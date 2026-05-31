// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
What: Minimal probe for Somnia JSON API fetchUint requests.
Run:  python scripts/somnia_vote_cli.py --config config.local.json compile
Use:  Deploy before the full voting contract to prove official JSON API request
      value, callback shape, raw result bytes, and uint decoding.
*/

import {ISomniaAgentCallback, ISomniaAgentPlatform, Request, Response, ResponseStatus} from "./interfaces/ISomniaAgent.sol";

contract JsonApiUintProbe is ISomniaAgentCallback {
    ISomniaAgentPlatform public immutable agentPlatform;
    address public owner;

    uint256 public jsonApiAgentId;
    bytes4 public jsonApiMethodSelector;
    uint256 public agentPricePerValidatorWei;
    uint256 public agentSubcommitteeSize;

    mapping(uint256 requestId => bool) public pendingRequests;

    uint256 public lastRequestId;
    ResponseStatus public lastStatus;
    bytes public lastRawResult;
    bool public lastDecodeOk;
    uint256 public lastDecodedUint;
    string public lastUrl;
    string public lastSelectorPath;
    uint8 public lastDecimals;

    event ProbeRequested(
        uint256 indexed requestId,
        string url,
        string selectorPath,
        uint8 decimals,
        uint256 requestValueWei
    );
    event ProbeResponseObserved(
        uint256 indexed requestId,
        uint256 indexed responseIndex,
        ResponseStatus status,
        uint256 receipt,
        address validator,
        uint256 executionCost,
        bytes result
    );
    event ProbeResolved(
        uint256 indexed requestId,
        ResponseStatus status,
        bool decodeOk,
        uint256 decodedUint,
        bytes rawResult
    );
    event AgentConfigUpdated(
        uint256 agentId,
        bytes4 methodSelector,
        uint256 pricePerValidatorWei,
        uint256 subcommitteeSize
    );
    event OwnershipTransferred(
        address indexed previousOwner,
        address indexed newOwner
    );
    event NativeReceived(address indexed sender, uint256 amountWei);

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    constructor(
        address agentPlatform_,
        uint256 jsonApiAgentId_,
        bytes4 jsonApiMethodSelector_,
        uint256 agentPricePerValidatorWei_,
        uint256 agentSubcommitteeSize_
    ) {
        require(agentPlatform_ != address(0), "platform required");
        require(agentSubcommitteeSize_ > 0, "subcommittee required");

        owner = msg.sender;
        agentPlatform = ISomniaAgentPlatform(agentPlatform_);
        jsonApiAgentId = jsonApiAgentId_;
        jsonApiMethodSelector = jsonApiMethodSelector_;
        agentPricePerValidatorWei = agentPricePerValidatorWei_;
        agentSubcommitteeSize = agentSubcommitteeSize_;
    }

    function requestUint(
        string calldata url,
        string calldata selectorPath,
        uint8 decimals
    ) external payable returns (uint256 requestId) {
        uint256 requestValueWei = quoteRequestValueWei();
        require(msg.value >= requestValueWei, "underfunded request");

        bytes memory payload = abi.encodeWithSelector(
            jsonApiMethodSelector,
            url,
            selectorPath,
            decimals
        );

        requestId = agentPlatform.createRequest{value: requestValueWei}(
            jsonApiAgentId,
            address(this),
            this.handleResponse.selector,
            payload
        );

        pendingRequests[requestId] = true;
        lastRequestId = requestId;
        lastUrl = url;
        lastSelectorPath = selectorPath;
        lastDecimals = decimals;

        emit ProbeRequested(
            requestId,
            url,
            selectorPath,
            decimals,
            requestValueWei
        );
    }

    function handleResponse(
        uint256 requestId,
        Response[] memory responses,
        ResponseStatus status,
        Request memory
    ) external override {
        require(msg.sender == address(agentPlatform), "only platform");
        require(pendingRequests[requestId], "unknown request");
        delete pendingRequests[requestId];

        lastRequestId = requestId;
        lastStatus = status;
        lastRawResult = "";
        lastDecodeOk = false;
        lastDecodedUint = 0;

        for (uint256 i = 0; i < responses.length; i++) {
            emit ProbeResponseObserved(
                requestId,
                i,
                responses[i].status,
                responses[i].receipt,
                responses[i].validator,
                responses[i].executionCost,
                responses[i].result
            );

            if (
                lastDecodeOk ||
                status != ResponseStatus.Success ||
                responses[i].status != ResponseStatus.Success
            ) {
                continue;
            }

            (bool decoded, uint256 value) = _tryDecodeUint(responses[i].result);
            lastRawResult = responses[i].result;
            lastDecodeOk = decoded;
            lastDecodedUint = value;
        }

        emit ProbeResolved(
            requestId,
            status,
            lastDecodeOk,
            lastDecodedUint,
            lastRawResult
        );
    }

    function setAgentConfig(
        uint256 newJsonApiAgentId,
        bytes4 newJsonApiMethodSelector,
        uint256 newAgentPricePerValidatorWei,
        uint256 newAgentSubcommitteeSize
    ) external onlyOwner {
        require(newAgentSubcommitteeSize > 0, "subcommittee required");
        jsonApiAgentId = newJsonApiAgentId;
        jsonApiMethodSelector = newJsonApiMethodSelector;
        agentPricePerValidatorWei = newAgentPricePerValidatorWei;
        agentSubcommitteeSize = newAgentSubcommitteeSize;
        emit AgentConfigUpdated(
            newJsonApiAgentId,
            newJsonApiMethodSelector,
            newAgentPricePerValidatorWei,
            newAgentSubcommitteeSize
        );
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "owner required");
        address previousOwner = owner;
        owner = newOwner;
        emit OwnershipTransferred(previousOwner, newOwner);
    }

    function withdraw(address payable to, uint256 amountWei) external onlyOwner {
        require(to != address(0), "recipient required");
        (bool ok, ) = to.call{value: amountWei}("");
        require(ok, "withdraw failed");
    }

    function quoteRequestValueWei() public view returns (uint256) {
        return
            agentPlatform.getRequestDeposit() +
            (agentPricePerValidatorWei * agentSubcommitteeSize);
    }

    function handleResponseSelector() external pure returns (bytes4) {
        return this.handleResponse.selector;
    }

    receive() external payable {
        emit NativeReceived(msg.sender, msg.value);
    }

    function _tryDecodeUint(
        bytes memory data
    ) private pure returns (bool decoded, uint256 value) {
        if (data.length != 32) {
            return (false, 0);
        }
        assembly {
            value := mload(add(data, 32))
        }
        return (true, value);
    }
}
