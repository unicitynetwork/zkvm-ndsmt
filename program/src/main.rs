#![no_main]
sp1_zkvm::entrypoint!(main);

use primitive_types::U256;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use lib::InputData2;


// Define the default 'empty' leaf and internal node value
fn default_leaf() -> U256 {
    U256::zero()
}

fn hash2(left: &U256, right: &U256) -> U256 {
    if *left == default_leaf() {
        *right
    } else if *right == default_leaf() {
        *left
    } else {
        // Convert U256 to big-endian bytes ([u8; 32])
        let mut left_bytes = [0u8; 32];
        let mut right_bytes = [0u8; 32];
        left.to_big_endian(&mut left_bytes);
        right.to_big_endian(&mut right_bytes);

        let mut hasher = Sha256::new();
        hasher.update(left_bytes);
        hasher.update(right_bytes);
        let result_hash = hasher.finalize();

        U256::from_big_endian(result_hash.as_slice())
    }
}

// Assumes leaves are sorted by key
fn compute_forest(
    proof: &[HashMap<u32, U256>],
    initial_leaves: &[(u32, U256)],
    depth: u32,
) -> Result<U256, String> {

    let mut current_nodes = initial_leaves.to_vec(); // Working copy

    // for level in (0..depth).rev() {
    let mut level = depth;
    while level > 0 {
        level -= 1;
        let mut next_level_nodes = Vec::new();
        let proof_for_level = proof
            .get(level as usize)
            .ok_or_else(|| format!("Sibling values from Proof are missing for level {}", level))?;

        let mut i = 0;
        while i < current_nodes.len() {
            let (k, kval) = current_nodes[i];
            let parent = k / 2;
            let is_left_child = (k & 1) == 0;
            let sibling_k = if is_left_child { k + 1 } else { k - 1 };
            // bitwise operations are less efficient
            //let parent = k >> 1;
            //let is_left_child = k % 2 == 0;
            //let sibling_k = k ^ 1;
            let sibling_val;

            // Check if the sibling happens to be the next node
            if is_left_child
                && i + 1 < current_nodes.len()
                && current_nodes[i + 1].0 == sibling_k
            {
                sibling_val = current_nodes[i + 1].1;
                i += 1; // Jump over the processed sibling
            } else {
                sibling_val = proof_for_level
                    .get(&sibling_k)
                    .cloned()
                    .unwrap_or_else(default_leaf);
            }

            let parent_val = if is_left_child {
                hash2(&kval, &sibling_val)
            } else {
                hash2(&sibling_val, &kval)
            };
            next_level_nodes.push((parent, parent_val));
            i += 1;
        }
        current_nodes = next_level_nodes;
    }
    assert_eq!(current_nodes.len(), 1, "Expected 1 node at level 0, found {}",
                current_nodes.len());
    return Ok(current_nodes[0].1);
}

// Verifies the non-deletion proof
fn verify_non_deletion(
    proof: &[HashMap<u32, U256>],
    old_root: U256,
    new_root: U256,
    keys: &[u32],
    values: &[U256],
    depth: u32,
) -> Result<bool, String> {
    let key_values: Vec<(u32, U256)> = keys
        .iter()
        .cloned()
        .zip(values.iter().cloned())
        .collect();
    // assuming keys in input json are already sorted
    // key_values.sort_by_key(|&(k, _)| k);

    // Create leaves for Step 1 ("old" state - blanks at key positions)
    let p1_leaves: Vec<(u32, U256)> = key_values
        .iter()
        .map(|&(k, _)| (k, default_leaf()))
        .collect();

    // Step 1: Compute old root based on proof and empty leaves
    let r1 = compute_forest(proof, &p1_leaves, depth)?;
    assert_eq!(r1, old_root, "Non-deletion proof root 1 mismatch: computed={}, expected={}",
            r1, old_root);

    // Step 2: Compute new root based on siblings from proof and inserted values
    let r2 = compute_forest(proof, &key_values, depth)?;
    assert_eq!(r2, new_root,
            "Non-deletion proof root 2 mismatch: computed={}, expected={}",
            r2, new_root
        );
    // all good
    sp1_zkvm::io::commit(&r1);
    sp1_zkvm::io::commit(&r2);
    sp1_zkvm::io::commit(&key_values.len()); // batch size
    Ok(true)
}

fn main() {

    let data = sp1_zkvm::io::read::<InputData2>();

    // Sanity checks
    assert_eq!(data.keys.len(), data.values.len(), "Error: Mismatched number of keys and values.");
    assert!(data.keys.len() > 0, "Error: empty batch.");
    assert!(data.proof.len().try_into() == Ok(data.depth),
            "Error: Proof length ({}) does not match depth ({}).",
            data.proof.len(),
            data.depth
        );
    assert!(data.depth > 0, "Error: depth.");

    // Verify the proof
    match verify_non_deletion(
        &data.proof, data.old_root, data.new_root, &data.keys, &data.values, data.depth) {
        Ok(true) => {
            //  println!(
            //      "Verification OK: {} -> {}",
            //      data.old_root, data.new_root
            //  );
        }
        Ok(false) => {
            panic!("Verification FAILED.");
        }
        Err(e) => {
            panic!("Verification Error: {}", e);
        }
    }
}
