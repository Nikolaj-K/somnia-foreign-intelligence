// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
What: Weighted, multi-collection NFT-gated voting contract for the Somnia demo.
Run:  python -m pytest test/test_nft_gated_vote.py
Use:  Deploy on Somnia testnet, fund with STT, then call
      vote(collectionId, tokenId, choice).

The contract is shaped for the real Somnia Agents platform callback. The live
path uses the documented fetchUint JSON API method against a `votingPower`
wrapper field. Local tests use MockSomniaAgentPlatform to create request IDs and
deliver typed results without needing the live JSON API agent or a deployed
wrapper endpoint.

AGENTATHON JURY DEBUG / DEMO ONLY:
This contract includes TODO(DEMO-REMOVE) debug/admin functions to make repeated
hackathon demos and testing easier. These functions intentionally give the
deployer/admin centralized powers. Remove all TODO(DEMO-REMOVE) code paths
before production or before presenting the contract as trustless.
*/

import {ISomniaAgentCallback, ISomniaAgentPlatform, Request, Response, ResponseStatus} from "./interfaces/ISomniaAgent.sol";

contract NftGatedVote is ISomniaAgentCallback {
    struct PendingVote {
        bool exists;
        address voter;
        uint8 collectionId;
        uint256 tokenId;
        uint8 choice;
        uint64 createdAt;
    }

    struct VoteRecord {
        bool hasVoted;
        uint8 collectionId;
        uint256 tokenId;
        address voter;
        uint8 choice;
        uint256 votingPower;
    }

    enum OwnershipResponseKind {
        Bool,
        Uint
    }

    string public constant OWNERSHIP_BOOL_SELECTOR = "owns";
    string public constant OWNERSHIP_UINT_SELECTOR = "votingPower";
    string public constant pollQuestion =
        "Which AI assistant should lead the next agentic workflow?";
    uint8 public constant OWNERSHIP_UINT_DECIMALS = 0;
    uint8 public constant QUILLS_COLLECTION_ID = 1;
    uint8 public constant BAYC_COLLECTION_ID = 2;
    uint8 public constant MAX_COLLECTION_ID = 2;
    uint64 public constant DEFAULT_PENDING_TIMEOUT_SECONDS = 1 days;

    ISomniaAgentPlatform public immutable agentPlatform;
    uint8 public immutable maxChoice;
    // TODO(DEMO-REMOVE): remove this agentathon debug/admin field before production/trustless deployment.
    address public immutable debugAdmin;

    address public owner;
    bool public paused;

    uint256 public jsonApiAgentId;
    bytes4 public jsonApiMethodSelector;
    uint256 public agentPricePerValidatorWei;
    uint256 public agentSubcommitteeSize;
    uint256 public rewardWei;
    OwnershipResponseKind public ownershipResponseKind;
    uint64 public pendingRequestTimeoutSeconds;
    string public baseOwnershipUrl;

    mapping(uint256 requestId => PendingVote) public pendingVotes;
    mapping(bytes32 voteKey => uint256 requestId) public voteKeyPendingRequest;
    mapping(bytes32 voteKey => VoteRecord) public voteRecords;
    mapping(uint8 choice => uint256) public voteCounts;

    bool private entered;

    event VoteRequested(
        uint256 indexed requestId,
        address indexed voter,
        uint8 indexed collectionId,
        uint256 tokenId,
        uint8 choice,
        string url,
        uint256 requestValueWei
    );
    event VoteRecorded(
        uint256 indexed requestId,
        address indexed voter,
        uint8 indexed collectionId,
        uint256 tokenId,
        uint8 choice,
        uint256 votingPower
    );
    event VoteRejected(
        uint256 indexed requestId,
        address indexed voter,
        uint8 indexed collectionId,
        uint256 tokenId,
        uint8 choice,
        uint256 votingPower,
        string reason
    );
    event IncentivePaid(
        uint256 indexed requestId,
        address indexed voter,
        uint256 amountWei
    );
    event IncentiveFailed(
        uint256 indexed requestId,
        address indexed voter,
        uint256 amountWei,
        string reason
    );
    event AgentResponseObserved(
        uint256 indexed requestId,
        uint256 indexed responseIndex,
        ResponseStatus status,
        uint256 receipt,
        address validator,
        uint256 executionCost,
        bytes result
    );
    event AgentConfigUpdated(
        uint256 agentId,
        bytes4 methodSelector,
        uint256 pricePerValidatorWei,
        uint256 subcommitteeSize,
        OwnershipResponseKind responseKind
    );
    event BaseOwnershipUrlUpdated(string oldUrl, string newUrl);
    event RewardWeiUpdated(uint256 oldRewardWei, uint256 newRewardWei);
    event PendingRequestTimeoutUpdated(
        uint64 oldTimeoutSeconds,
        uint64 newTimeoutSeconds
    );
    event Paused();
    event Unpaused();
    event OwnershipTransferred(
        address indexed previousOwner,
        address indexed newOwner
    );
    event NativeReceived(address indexed sender, uint256 amountWei);
    event DebugVoteVoided(
        uint8 indexed collectionId,
        uint256 indexed tokenId,
        address indexed previousVoter,
        uint8 previousChoice,
        uint256 previousWeight
    );
    event DebugPendingRequestCancelled(
        uint256 indexed requestId,
        address indexed voter,
        uint8 indexed collectionId,
        uint256 tokenId,
        uint8 choice
    );
    event DebugSTTWithdrawn(address indexed to, uint256 amountWei);

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    // TODO(DEMO-REMOVE): remove this agentathon debug/admin modifier before production/trustless deployment.
    modifier onlyDebugAdmin() {
        require(msg.sender == debugAdmin, "only debug admin");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "paused");
        _;
    }

    modifier nonReentrant() {
        require(!entered, "reentrant");
        entered = true;
        _;
        entered = false;
    }

    constructor(
        address agentPlatform_,
        uint256 jsonApiAgentId_,
        bytes4 jsonApiMethodSelector_,
        uint256 agentPricePerValidatorWei_,
        uint256 agentSubcommitteeSize_,
        string memory baseOwnershipUrl_,
        OwnershipResponseKind ownershipResponseKind_,
        uint256 rewardWei_,
        uint8 maxChoice_
    ) {
        require(agentPlatform_ != address(0), "platform required");
        require(maxChoice_ > 0, "max choice required");
        require(agentSubcommitteeSize_ > 0, "subcommittee required");
        require(
            isValidBaseOwnershipUrl(baseOwnershipUrl_),
            "invalid base ownership url"
        );

        owner = msg.sender;
        debugAdmin = msg.sender;
        agentPlatform = ISomniaAgentPlatform(agentPlatform_);
        jsonApiAgentId = jsonApiAgentId_;
        jsonApiMethodSelector = jsonApiMethodSelector_;
        agentPricePerValidatorWei = agentPricePerValidatorWei_;
        agentSubcommitteeSize = agentSubcommitteeSize_;
        baseOwnershipUrl = baseOwnershipUrl_;
        ownershipResponseKind = ownershipResponseKind_;
        pendingRequestTimeoutSeconds = DEFAULT_PENDING_TIMEOUT_SECONDS;
        rewardWei = rewardWei_;
        maxChoice = maxChoice_;
    }

    function vote(
        uint8 collectionId,
        uint256 tokenId,
        uint8 choice
    ) external whenNotPaused nonReentrant returns (uint256 requestId) {
        require(isSupportedCollection(collectionId), "unsupported collection");
        require(choice > 0, "choice zero");
        require(choice <= maxChoice, "choice too high");

        bytes32 voteKey = voteKeyFor(collectionId, tokenId);
        require(!voteRecords[voteKey].hasVoted, "token already voted");
        require(voteKeyPendingRequest[voteKey] == 0, "token request pending");

        string memory url = ownershipUrl(collectionId, msg.sender, tokenId);
        bytes memory payload = jsonApiPayloadForUrl(url);
        uint256 requestValueWei = quoteRequestValueWei();

        requestId = agentPlatform.createRequest{value: requestValueWei}(
            jsonApiAgentId,
            address(this),
            this.handleResponse.selector,
            payload
        );

        pendingVotes[requestId] = PendingVote({
            exists: true,
            voter: msg.sender,
            collectionId: collectionId,
            tokenId: tokenId,
            choice: choice,
            createdAt: uint64(block.timestamp)
        });
        voteKeyPendingRequest[voteKey] = requestId;

        emit VoteRequested(
            requestId,
            msg.sender,
            collectionId,
            tokenId,
            choice,
            url,
            requestValueWei
        );
    }

    function handleResponse(
        uint256 requestId,
        Response[] memory responses,
        ResponseStatus status,
        Request memory
    ) external override nonReentrant {
        require(msg.sender == address(agentPlatform), "only platform");

        PendingVote memory pendingVote = pendingVotes[requestId];
        if (!pendingVote.exists) {
            emit VoteRejected(
                requestId,
                address(0),
                0,
                0,
                0,
                0,
                "missing_pending_vote"
            );
            return;
        }
        delete pendingVotes[requestId];

        bytes32 voteKey = voteKeyFor(
            pendingVote.collectionId,
            pendingVote.tokenId
        );
        if (voteKeyPendingRequest[voteKey] == requestId) {
            delete voteKeyPendingRequest[voteKey];
        }

        (bool hasResult, uint256 votingPower) = _firstSuccessfulVotingPowerResponse(
            requestId,
            pendingVote.collectionId,
            responses
        );
        if (status != ResponseStatus.Success) {
            _emitVoteRejected(
                requestId,
                pendingVote,
                votingPower,
                "agent_status_not_success"
            );
            return;
        }
        if (!hasResult) {
            _emitVoteRejected(
                requestId,
                pendingVote,
                0,
                "no_success_ownership_response"
            );
            return;
        }
        if (votingPower == 0) {
            _emitVoteRejected(
                requestId,
                pendingVote,
                0,
                "ownership_check_false"
            );
            return;
        }
        if (voteRecords[voteKey].hasVoted) {
            _emitVoteRejected(
                requestId,
                pendingVote,
                votingPower,
                "token_already_voted"
            );
            return;
        }

        voteRecords[voteKey] = VoteRecord({
            hasVoted: true,
            collectionId: pendingVote.collectionId,
            tokenId: pendingVote.tokenId,
            voter: pendingVote.voter,
            choice: pendingVote.choice,
            votingPower: votingPower
        });
        voteCounts[pendingVote.choice] += votingPower;

        emit VoteRecorded(
            requestId,
            pendingVote.voter,
            pendingVote.collectionId,
            pendingVote.tokenId,
            pendingVote.choice,
            votingPower
        );
        _payReward(requestId, pendingVote.voter);
    }

    function setBaseOwnershipUrl(
        string calldata newBaseOwnershipUrl
    ) external onlyOwner {
        require(
            isValidBaseOwnershipUrl(newBaseOwnershipUrl),
            "invalid base ownership url"
        );
        string memory oldUrl = baseOwnershipUrl;
        baseOwnershipUrl = newBaseOwnershipUrl;
        emit BaseOwnershipUrlUpdated(oldUrl, newBaseOwnershipUrl);
    }

    function setAgentConfig(
        uint256 newJsonApiAgentId,
        bytes4 newJsonApiMethodSelector,
        uint256 newAgentPricePerValidatorWei,
        uint256 newAgentSubcommitteeSize,
        OwnershipResponseKind newOwnershipResponseKind
    ) external onlyOwner {
        require(newAgentSubcommitteeSize > 0, "subcommittee required");
        jsonApiAgentId = newJsonApiAgentId;
        jsonApiMethodSelector = newJsonApiMethodSelector;
        agentPricePerValidatorWei = newAgentPricePerValidatorWei;
        agentSubcommitteeSize = newAgentSubcommitteeSize;
        ownershipResponseKind = newOwnershipResponseKind;
        emit AgentConfigUpdated(
            newJsonApiAgentId,
            newJsonApiMethodSelector,
            newAgentPricePerValidatorWei,
            newAgentSubcommitteeSize,
            newOwnershipResponseKind
        );
    }

    function setRewardWei(uint256 newRewardWei) external onlyOwner {
        uint256 oldRewardWei = rewardWei;
        rewardWei = newRewardWei;
        emit RewardWeiUpdated(oldRewardWei, newRewardWei);
    }

    function setPendingRequestTimeoutSeconds(
        uint64 newTimeoutSeconds
    ) external onlyOwner {
        require(newTimeoutSeconds > 0, "timeout required");
        uint64 oldTimeoutSeconds = pendingRequestTimeoutSeconds;
        pendingRequestTimeoutSeconds = newTimeoutSeconds;
        emit PendingRequestTimeoutUpdated(
            oldTimeoutSeconds,
            newTimeoutSeconds
        );
    }

    function releaseExpiredPendingVote(uint256 requestId) external {
        PendingVote memory pendingVote = pendingVotes[requestId];
        require(pendingVote.exists, "missing pending vote");
        require(
            block.timestamp >=
                uint256(pendingVote.createdAt) + pendingRequestTimeoutSeconds,
            "pending vote not expired"
        );

        delete pendingVotes[requestId];
        bytes32 voteKey = voteKeyFor(
            pendingVote.collectionId,
            pendingVote.tokenId
        );
        if (voteKeyPendingRequest[voteKey] == requestId) {
            delete voteKeyPendingRequest[voteKey];
        }
        _emitVoteRejected(
            requestId,
            pendingVote,
            0,
            "pending_vote_expired"
        );
    }

    function pause() external onlyOwner {
        paused = true;
        emit Paused();
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused();
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

    /*
     * AGENTATHON JURY DEBUG / DEMO ONLY:
     * Remove before production or before presenting this contract as trustless.
     * These functions intentionally give the deployer/admin centralized powers
     * and are included only to make repeated hackathon demos and testing easier.
     */

    // TODO(DEMO-REMOVE): remove this debug/admin function before production/trustless deployment.
    function debugOnlyVoidVote(
        uint8 collectionId,
        uint256 tokenId
    ) public onlyDebugAdmin {
        bytes32 voteKey = voteKeyFor(collectionId, tokenId);
        VoteRecord memory previous = voteRecords[voteKey];
        require(previous.hasVoted, "token has not voted");
        uint256 previousCount = voteCounts[previous.choice];
        require(previousCount >= previous.votingPower, "vote count underflow");

        voteCounts[previous.choice] = previousCount - previous.votingPower;
        delete voteRecords[voteKey];

        emit DebugVoteVoided(
            collectionId,
            tokenId,
            previous.voter,
            previous.choice,
            previous.votingPower
        );
    }

    // TODO(DEMO-REMOVE): compatibility alias for the first Quills-only demo.
    function debugOnlyVoidVote(uint256 tokenId) external onlyDebugAdmin {
        debugOnlyVoidVote(QUILLS_COLLECTION_ID, tokenId);
    }

    // TODO(DEMO-REMOVE): remove this debug/admin function before production/trustless deployment.
    function debugOnlyCancelPendingRequest(
        uint256 requestId
    ) external onlyDebugAdmin {
        PendingVote memory pendingVote = pendingVotes[requestId];
        require(pendingVote.exists, "missing pending vote");

        delete pendingVotes[requestId];
        bytes32 voteKey = voteKeyFor(
            pendingVote.collectionId,
            pendingVote.tokenId
        );
        if (voteKeyPendingRequest[voteKey] == requestId) {
            delete voteKeyPendingRequest[voteKey];
        }

        emit DebugPendingRequestCancelled(
            requestId,
            pendingVote.voter,
            pendingVote.collectionId,
            pendingVote.tokenId,
            pendingVote.choice
        );
    }

    // TODO(DEMO-REMOVE): remove this debug/admin function before production/trustless deployment.
    function debugOnlyWithdrawSTT(
        address payable to,
        uint256 amountWei
    ) public onlyDebugAdmin {
        require(to != address(0), "recipient required");
        require(amountWei <= address(this).balance, "insufficient balance");
        (bool ok, ) = to.call{value: amountWei}("");
        require(ok, "withdraw failed");
        emit DebugSTTWithdrawn(to, amountWei);
    }

    // TODO(DEMO-REMOVE): remove this debug/admin function before production/trustless deployment.
    function debugOnlyWithdrawAllSTT(
        address payable to
    ) external onlyDebugAdmin {
        debugOnlyWithdrawSTT(to, address(this).balance);
    }

    function quoteRequestValueWei() public view returns (uint256) {
        return
            agentPlatform.getRequestDeposit() +
            (agentPricePerValidatorWei * agentSubcommitteeSize);
    }

    function voteKeyFor(
        uint8 collectionId,
        uint256 tokenId
    ) public pure returns (bytes32) {
        return keccak256(abi.encode(collectionId, tokenId));
    }

    function hasTokenVoted(
        uint8 collectionId,
        uint256 tokenId
    ) public view returns (bool) {
        return voteRecords[voteKeyFor(collectionId, tokenId)].hasVoted;
    }

    // Compatibility alias for the first Quills-only demo.
    function hasTokenVoted(uint256 tokenId) external view returns (bool) {
        return hasTokenVoted(QUILLS_COLLECTION_ID, tokenId);
    }

    function getTokenVote(
        uint8 collectionId,
        uint256 tokenId
    ) public view returns (uint8) {
        return voteRecords[voteKeyFor(collectionId, tokenId)].choice;
    }

    // Compatibility alias for the first Quills-only demo.
    function getTokenVote(uint256 tokenId) external view returns (uint8) {
        return getTokenVote(QUILLS_COLLECTION_ID, tokenId);
    }

    function tokenVoter(
        uint8 collectionId,
        uint256 tokenId
    ) public view returns (address) {
        return voteRecords[voteKeyFor(collectionId, tokenId)].voter;
    }

    // Compatibility alias for the first Quills-only demo.
    function tokenVoter(uint256 tokenId) external view returns (address) {
        return tokenVoter(QUILLS_COLLECTION_ID, tokenId);
    }

    function tokenVotingPower(
        uint8 collectionId,
        uint256 tokenId
    ) external view returns (uint256) {
        return voteRecords[voteKeyFor(collectionId, tokenId)].votingPower;
    }

    function tokenPendingRequest(
        uint8 collectionId,
        uint256 tokenId
    ) public view returns (uint256) {
        return voteKeyPendingRequest[voteKeyFor(collectionId, tokenId)];
    }

    // Compatibility alias for the first Quills-only demo.
    function tokenPendingRequest(
        uint256 tokenId
    ) external view returns (uint256) {
        return tokenPendingRequest(QUILLS_COLLECTION_ID, tokenId);
    }

    function getVoteRecord(
        uint8 collectionId,
        uint256 tokenId
    )
        external
        view
        returns (
            bool hasVoted,
            uint8 recordedCollectionId,
            uint256 recordedTokenId,
            address voter,
            uint8 choice,
            uint256 votingPower
        )
    {
        VoteRecord memory record = voteRecords[
            voteKeyFor(collectionId, tokenId)
        ];
        return (
            record.hasVoted,
            record.collectionId,
            record.tokenId,
            record.voter,
            record.choice,
            record.votingPower
        );
    }

    function getVoteCount(uint8 choice) external view returns (uint256) {
        return voteCounts[choice];
    }

    function getChoiceCount(uint8 choice) external view returns (uint256) {
        return voteCounts[choice];
    }

    function getAllChoiceCounts()
        external
        view
        returns (uint256[] memory counts)
    {
        counts = new uint256[](maxChoice);
        for (uint256 choice = 1; choice <= maxChoice; choice++) {
            counts[choice - 1] = voteCounts[uint8(choice)];
        }
    }

    function leadingChoice()
        external
        view
        returns (uint8 choice, uint256 votes, bool hasVotes, bool isTie)
    {
        for (uint256 candidate = 1; candidate <= maxChoice; candidate++) {
            uint256 count = voteCounts[uint8(candidate)];
            if (count == 0) {
                continue;
            }
            if (!hasVotes || count > votes) {
                choice = uint8(candidate);
                votes = count;
                hasVotes = true;
                isTie = false;
            } else if (count == votes) {
                isTie = true;
            }
        }
    }

    function choiceLabel(uint8 choice) public pure returns (string memory) {
        if (choice == 1) {
            return "ChatGPT";
        }
        if (choice == 2) {
            return "Claude";
        }
        if (choice == 3) {
            return "DeepSeek";
        }
        return "";
    }

    function maxCollectionId() external pure returns (uint8) {
        return MAX_COLLECTION_ID;
    }

    function supportedCollectionIds()
        external
        pure
        returns (uint8[] memory ids)
    {
        ids = new uint8[](2);
        ids[0] = QUILLS_COLLECTION_ID;
        ids[1] = BAYC_COLLECTION_ID;
    }

    function isSupportedCollection(
        uint8 collectionId
    ) public pure returns (bool) {
        return
            collectionId == QUILLS_COLLECTION_ID ||
            collectionId == BAYC_COLLECTION_ID;
    }

    function collectionLabel(
        uint8 collectionId
    ) public pure returns (string memory) {
        if (collectionId == QUILLS_COLLECTION_ID) {
            return "quills-adventure";
        }
        if (collectionId == BAYC_COLLECTION_ID) {
            return "bored-ape-yacht-club";
        }
        return "";
    }

    function collectionDisplayLabel(
        uint8 collectionId
    ) public pure returns (string memory) {
        if (collectionId == QUILLS_COLLECTION_ID) {
            return "Quills Adventure";
        }
        if (collectionId == BAYC_COLLECTION_ID) {
            return "Bored Ape Yacht Club";
        }
        return "";
    }

    function collectionChainLabel(
        uint8 collectionId
    ) public pure returns (string memory) {
        if (collectionId == QUILLS_COLLECTION_ID) {
            return "somnia-mainnet";
        }
        if (collectionId == BAYC_COLLECTION_ID) {
            return "ethereum-mainnet";
        }
        return "";
    }

    function collectionVotingPower(
        uint8 collectionId
    ) public pure returns (uint256) {
        if (collectionId == QUILLS_COLLECTION_ID) {
            return 1;
        }
        if (collectionId == BAYC_COLLECTION_ID) {
            return 2;
        }
        return 0;
    }

    function ownershipUrl(
        uint8 collectionId,
        address wallet,
        uint256 tokenId
    ) public view returns (string memory) {
        require(isSupportedCollection(collectionId), "unsupported collection");
        return
            string.concat(
                baseOwnershipUrl,
                "?collectionId=",
                _uintToString(collectionId),
                "&wallet=",
                _addressToHexString(wallet),
                "&tokenId=",
                _uintToString(tokenId)
            );
    }

    // Compatibility alias for the first Quills-only demo.
    function ownershipUrl(
        address wallet,
        uint256 tokenId
    ) public view returns (string memory) {
        return ownershipUrl(QUILLS_COLLECTION_ID, wallet, tokenId);
    }

    function ownershipSelectorPath() public view returns (string memory) {
        if (ownershipResponseKind == OwnershipResponseKind.Uint) {
            return OWNERSHIP_UINT_SELECTOR;
        }
        return OWNERSHIP_BOOL_SELECTOR;
    }

    function jsonApiPayload(
        uint8 collectionId,
        address wallet,
        uint256 tokenId
    ) external view returns (bytes memory) {
        return jsonApiPayloadForUrl(ownershipUrl(collectionId, wallet, tokenId));
    }

    // Compatibility alias for the first Quills-only demo.
    function jsonApiPayload(
        address wallet,
        uint256 tokenId
    ) external view returns (bytes memory) {
        return jsonApiPayloadForUrl(
            ownershipUrl(QUILLS_COLLECTION_ID, wallet, tokenId)
        );
    }

    function handleResponseSelector() external pure returns (bytes4) {
        return this.handleResponse.selector;
    }

    function isValidBaseOwnershipUrl(
        string memory candidate
    ) public pure returns (bool) {
        bytes memory raw = bytes(candidate);
        if (raw.length == 0 || _containsByte(raw, "?")) {
            return false;
        }
        return _startsWith(raw, "http://") || _startsWith(raw, "https://");
    }

    receive() external payable {
        emit NativeReceived(msg.sender, msg.value);
    }

    function jsonApiPayloadForUrl(
        string memory url
    ) private view returns (bytes memory) {
        if (ownershipResponseKind == OwnershipResponseKind.Uint) {
            return
                abi.encodeWithSelector(
                    jsonApiMethodSelector,
                    url,
                    OWNERSHIP_UINT_SELECTOR,
                    OWNERSHIP_UINT_DECIMALS
                );
        }

        return
            abi.encodeWithSelector(
                jsonApiMethodSelector,
                url,
                OWNERSHIP_BOOL_SELECTOR
            );
    }

    function _firstSuccessfulVotingPowerResponse(
        uint256 requestId,
        uint8 collectionId,
        Response[] memory responses
    ) private returns (bool hasResult, uint256 votingPower) {
        for (uint256 i = 0; i < responses.length; i++) {
            emit AgentResponseObserved(
                requestId,
                i,
                responses[i].status,
                responses[i].receipt,
                responses[i].validator,
                responses[i].executionCost,
                responses[i].result
            );

            if (hasResult || responses[i].status != ResponseStatus.Success) {
                continue;
            }

            (bool decoded, uint256 value) = _tryDecodeVotingPowerResponse(
                collectionId,
                responses[i].result
            );
            if (decoded) {
                hasResult = true;
                votingPower = value;
            }
        }
    }

    function _tryDecodeVotingPowerResponse(
        uint8 collectionId,
        bytes memory data
    ) private view returns (bool decoded, uint256 votingPower) {
        if (data.length != 32) {
            return (false, 0);
        }

        uint256 rawValue;
        assembly {
            rawValue := mload(add(data, 32))
        }

        if (ownershipResponseKind == OwnershipResponseKind.Bool) {
            if (rawValue == 0) {
                return (true, 0);
            }
            if (rawValue == 1) {
                return (true, collectionVotingPower(collectionId));
            }
            return (false, 0);
        }

        return (true, rawValue);
    }

    function _emitVoteRejected(
        uint256 requestId,
        PendingVote memory pendingVote,
        uint256 votingPower,
        string memory reason
    ) private {
        emit VoteRejected(
            requestId,
            pendingVote.voter,
            pendingVote.collectionId,
            pendingVote.tokenId,
            pendingVote.choice,
            votingPower,
            reason
        );
    }

    function _payReward(uint256 requestId, address voter) private {
        if (rewardWei == 0) {
            return;
        }
        if (address(this).balance < rewardWei) {
            emit IncentiveFailed(
                requestId,
                voter,
                rewardWei,
                "insufficient_contract_balance"
            );
            return;
        }

        (bool ok, ) = payable(voter).call{value: rewardWei}("");
        if (ok) {
            emit IncentivePaid(requestId, voter, rewardWei);
        } else {
            emit IncentiveFailed(requestId, voter, rewardWei, "transfer_failed");
        }
    }

    function _uintToString(
        uint256 value
    ) private pure returns (string memory) {
        if (value == 0) {
            return "0";
        }

        uint256 temp = value;
        uint256 digits;
        while (temp != 0) {
            digits++;
            temp /= 10;
        }

        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits -= 1;
            buffer[digits] = bytes1(uint8(48 + uint256(value % 10)));
            value /= 10;
        }
        return string(buffer);
    }

    function _addressToHexString(
        address account
    ) private pure returns (string memory) {
        bytes20 value = bytes20(account);
        bytes16 alphabet = "0123456789abcdef";
        bytes memory buffer = new bytes(42);
        buffer[0] = "0";
        buffer[1] = "x";

        for (uint256 i = 0; i < 20; i++) {
            buffer[2 + i * 2] = alphabet[uint8(value[i] >> 4)];
            buffer[3 + i * 2] = alphabet[uint8(value[i] & 0x0f)];
        }

        return string(buffer);
    }

    function _startsWith(
        bytes memory raw,
        bytes memory prefix
    ) private pure returns (bool) {
        if (raw.length < prefix.length) {
            return false;
        }
        for (uint256 i = 0; i < prefix.length; i++) {
            if (raw[i] != prefix[i]) {
                return false;
            }
        }
        return true;
    }

    function _containsByte(
        bytes memory raw,
        bytes1 needle
    ) private pure returns (bool) {
        for (uint256 i = 0; i < raw.length; i++) {
            if (raw[i] == needle) {
                return true;
            }
        }
        return false;
    }
}
