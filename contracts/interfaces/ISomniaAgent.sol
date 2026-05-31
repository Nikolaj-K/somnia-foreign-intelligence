// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
What: Minimal Somnia Agents platform types and interfaces used by this demo.
Use:  Imported by NftGatedVote and the local mock platform tests.

The struct layout mirrors the callback contract that was previously tested in
the adjacent Somnia Agents project. Keeping this ABI in one file makes callback
selector drift easier to spot before spending testnet STT.
*/

enum ConsensusType {
    Majority,
    Threshold
}

enum ResponseStatus {
    None,
    Pending,
    Success,
    Failed,
    TimedOut
}

struct Response {
    address validator;
    bytes result;
    ResponseStatus status;
    uint256 receipt;
    uint256 timestamp;
    uint256 executionCost;
}

struct Request {
    uint256 id;
    address requester;
    address callbackAddress;
    bytes4 callbackSelector;
    address[] subcommittee;
    Response[] responses;
    uint256 responseCount;
    uint256 failureCount;
    uint256 threshold;
    uint256 createdAt;
    uint256 deadline;
    ResponseStatus status;
    ConsensusType consensusType;
    uint256 remainingBudget;
    uint256 perAgentBudget;
}

interface ISomniaAgentPlatform {
    function createRequest(
        uint256 agentId,
        address callbackAddress,
        bytes4 callbackSelector,
        bytes calldata payload
    ) external payable returns (uint256 requestId);

    function getRequestDeposit() external view returns (uint256);
}

interface ISomniaAgentCallback {
    function handleResponse(
        uint256 requestId,
        Response[] memory responses,
        ResponseStatus status,
        Request memory details
    ) external;
}
