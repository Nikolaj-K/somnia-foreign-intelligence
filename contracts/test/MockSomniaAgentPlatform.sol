// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
What: Local mock for SomniaAgents.createRequest and callback delivery.
Run:  python -m pytest test/test_nft_gated_vote.py

This mock lets tests exercise the async request/callback lifecycle without a
live JSON API agent, public wrapper URL, or STT spend.
*/

import {ConsensusType, ISomniaAgentCallback, ISomniaAgentPlatform, Request, Response, ResponseStatus} from "../interfaces/ISomniaAgent.sol";

contract MockSomniaAgentPlatform is ISomniaAgentPlatform {
    struct StoredRequest {
        bool exists;
        address requester;
        uint256 agentId;
        address callbackAddress;
        bytes4 callbackSelector;
        uint256 valueWei;
        bytes payload;
    }

    uint256 public nextRequestId = 1;
    uint256 public requestDepositWei;
    address public immutable owner;

    mapping(uint256 requestId => StoredRequest) public requests;

    event MockRequestCreated(
        uint256 indexed requestId,
        address indexed requester,
        uint256 indexed agentId,
        address callbackAddress,
        bytes4 callbackSelector,
        uint256 valueWei,
        bytes payload
    );
    event MockRequestFulfilled(
        uint256 indexed requestId,
        ResponseStatus status
    );

    constructor(uint256 requestDepositWei_) {
        owner = msg.sender;
        requestDepositWei = requestDepositWei_;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    function setRequestDepositWei(uint256 requestDepositWei_) external onlyOwner {
        requestDepositWei = requestDepositWei_;
    }

    function getRequestDeposit() external view override returns (uint256) {
        return requestDepositWei;
    }

    function createRequest(
        uint256 agentId,
        address callbackAddress,
        bytes4 callbackSelector,
        bytes calldata payload
    ) external payable override returns (uint256 requestId) {
        requestId = nextRequestId;
        nextRequestId += 1;

        requests[requestId] = StoredRequest({
            exists: true,
            requester: msg.sender,
            agentId: agentId,
            callbackAddress: callbackAddress,
            callbackSelector: callbackSelector,
            valueWei: msg.value,
            payload: payload
        });

        emit MockRequestCreated(
            requestId,
            msg.sender,
            agentId,
            callbackAddress,
            callbackSelector,
            msg.value,
            payload
        );
    }

    function fulfillBool(uint256 requestId, bool owns) external onlyOwner {
        Response[] memory responses = new Response[](1);
        responses[0] = Response({
            validator: address(this),
            result: abi.encode(owns),
            status: ResponseStatus.Success,
            receipt: requestId,
            timestamp: block.timestamp,
            executionCost: 0
        });
        _deliver(requestId, responses, ResponseStatus.Success);
    }

    function fulfillUint(uint256 requestId, uint256 value) external onlyOwner {
        Response[] memory responses = new Response[](1);
        responses[0] = Response({
            validator: address(this),
            result: abi.encode(value),
            status: ResponseStatus.Success,
            receipt: requestId,
            timestamp: block.timestamp,
            executionCost: 0
        });
        _deliver(requestId, responses, ResponseStatus.Success);
    }

    function fulfillBoolWithStatus(
        uint256 requestId,
        bool owns,
        ResponseStatus overallStatus
    ) external onlyOwner {
        Response[] memory responses = new Response[](1);
        responses[0] = Response({
            validator: address(this),
            result: abi.encode(owns),
            status: ResponseStatus.Success,
            receipt: requestId,
            timestamp: block.timestamp,
            executionCost: 0
        });
        _deliver(requestId, responses, overallStatus);
    }

    function fulfillFailure(
        uint256 requestId,
        bytes calldata failureResult
    ) external onlyOwner {
        Response[] memory responses = new Response[](1);
        responses[0] = Response({
            validator: address(this),
            result: failureResult,
            status: ResponseStatus.Failed,
            receipt: requestId,
            timestamp: block.timestamp,
            executionCost: 0
        });
        _deliver(requestId, responses, ResponseStatus.Failed);
    }

    function fulfillRawSuccess(
        uint256 requestId,
        bytes calldata rawResult
    ) external onlyOwner {
        Response[] memory responses = new Response[](1);
        responses[0] = Response({
            validator: address(this),
            result: rawResult,
            status: ResponseStatus.Success,
            receipt: requestId,
            timestamp: block.timestamp,
            executionCost: 0
        });
        _deliver(requestId, responses, ResponseStatus.Success);
    }

    function _deliver(
        uint256 requestId,
        Response[] memory responses,
        ResponseStatus status
    ) private {
        StoredRequest memory storedRequest = requests[requestId];
        require(storedRequest.exists, "missing request");

        address[] memory subcommittee = new address[](1);
        subcommittee[0] = address(this);

        Request memory details = Request({
            id: requestId,
            requester: storedRequest.requester,
            callbackAddress: storedRequest.callbackAddress,
            callbackSelector: storedRequest.callbackSelector,
            subcommittee: subcommittee,
            responses: responses,
            responseCount: responses.length,
            failureCount: status == ResponseStatus.Success ? 0 : responses.length,
            threshold: 1,
            createdAt: block.timestamp,
            deadline: block.timestamp,
            status: status,
            consensusType: ConsensusType.Majority,
            remainingBudget: storedRequest.valueWei,
            perAgentBudget: 0
        });

        ISomniaAgentCallback(storedRequest.callbackAddress).handleResponse(
            requestId,
            responses,
            status,
            details
        );

        emit MockRequestFulfilled(requestId, status);
    }
}
