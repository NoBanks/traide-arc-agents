// SPDX-License-Identifier: MIT
pragma solidity 0.8.25;

/// @title ArcReceiptAnchor
/// @notice Anchors keeper receipt hashes for the TRAIDE agents running on Arc.
/// @dev Deliberately minimal. The alternative considered was a self transfer
///      carrying the hash as calldata, which is cheaper but leaves nothing
///      queryable: a verifier would have to scan every transaction from the
///      agent to find anchors. This contract costs a little more gas and gives
///      three things a memo cannot: an indexed event a verifier can filter on,
///      a first-seen block per hash so a receipt cannot be backdated, and a
///      running total that the dashboard reads with one eth_call.
///      No owner, no upgrade path, no admin. Anyone may attest.
contract ArcReceiptAnchor {
    /// @notice Block timestamp of the first attestation for a receipt hash.
    mapping(bytes32 => uint256) public attestedAt;

    /// @notice Address that first attested a receipt hash.
    mapping(bytes32 => address) public attestedBy;

    /// @notice Number of distinct receipt hashes anchored.
    uint256 public total;

    event Attested(
        address indexed attester,
        bytes32 indexed receiptHash,
        bytes32 indexed agent,
        uint256 timestamp
    );

    error AlreadyAttested(bytes32 receiptHash);
    error EmptyHash();

    /// @param receiptHash sha256 of the canonical receipt JSON, as produced by
    ///        arc_agents.receipts.receipt_hash, which uses the same
    ///        canonicalization rule as traide-keeper.
    /// @param agent short name of the agent, right padded into bytes32, so the
    ///        event can be filtered per agent without an off chain index.
    function attest(bytes32 receiptHash, bytes32 agent) external {
        if (receiptHash == bytes32(0)) revert EmptyHash();
        if (attestedAt[receiptHash] != 0) revert AlreadyAttested(receiptHash);
        attestedAt[receiptHash] = block.timestamp;
        attestedBy[receiptHash] = msg.sender;
        unchecked {
            total += 1;
        }
        emit Attested(msg.sender, receiptHash, agent, block.timestamp);
    }

    /// @notice True when the hash has been anchored on this chain.
    function isAttested(bytes32 receiptHash) external view returns (bool) {
        return attestedAt[receiptHash] != 0;
    }
}
