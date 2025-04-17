# Problem

Problem is the same as in previous explorations[^1]: proving the correct operation of Unicity's aggregation layer. See the Whitepaper, Appendix B[^2] how it is set up.

We are using SP1 zkVM[^3] generated STARK, proving that consistency proof of service is valid. The STARK proof is almost constant size.

Let's drop input transaction batch from public inputs. The inclusion/non-inclusion proofs work without ZK, based on data structures alone. The public data is then SMT root hash before inserting the batch, after inserting the batch, and batch size. Private _witness_ is the transaction batch (as keys and values) and hash-based consistency proof, as defined in [^2].


## Security Model

We have a fixed circuit written as Rust program. As a commitment to the "right" verification program we use prover key, generated during setup. Its contents is: commitment to the preprocessed traces, the starting Program Counter register, The starting global digest of the program, after incorporating the initial memory; the chip information, the chip ordering. Probably prover config -- underlying finite field, PCS scheme, etc. -- as well.

For verification, we obtain the prover key hash and authenticate it off-band. One way to get the hash is
```
cd program
cargo prove vkey --program ndproof-program
```
or programmatically
```rs
const ELF: &[u8] = include_elf!("ndproof-program");
...
let client = ProverClient::builder().cpu().build();
let (_, vk) = client.setup(ELF);
println!("Verification Key Hash: {}", vk.vk.bytes32());
```

After verifying the proof (`client.verify(&proof, &vk)`), we are sure that `proof: SP1ProofWithPublicValues` is valid. The proof data structure embeds its validated "instance", or public parameters. Based on these parameters we check that indeed, the right thing was validated by our program. In our case the instance is defined by old root hash, new root hash, and the batch size. Now we know, that the proof (this is the hash-based non-deletion proof of SMT's change being consistent) verification algorithm was executed correctly, and this algorithm was happy with its public and private inputs; and thereby the batch of additions inserted into the SMT was also executed correctly: started its processing with initial state and after inserting n transactions (and not removing nor modifying any existing leaves) reached the final summary state. Obviously, before-state and after-state must be authentic. This is achieved by committing them to append-only dictionary / blockchain / Unicity's BFT layer.

We do not care about privacy of the "secret" witness. Not sure if used STARKs implementations provide it neither. So, no zk in zk-SNARKs, just proof of computational integrity.


## Walkthrough

```console
# Make sure that rust is available. Install rustup etc. Check:
rustup toolchain list
# Install sp1 toolchain, see
# https://docs.succinct.xyz/docs/sp1/getting-started/install
# and test:
cargo prove --version
# generate test data, see loops at the end of ndsmt.py how to change batch size,
# number of pregenerated leaves, etc.
cd script
python3 ndsmt.py > input.json
# run.
RUSTFLAGS='-C target-cpu=native' cargo run --release
```


## Optimization ideas
The elephant is the underlying hashing function.

At the time of writing, SP1 has precompiles for SHA2 and SHA3/Keccak, so these are somewhat accelerated. See program output -- which precompiles (aka coprocessors, chips) are used and how many times, e.g., `... SHA_EXTEND: 3552, SHA_COMPRESS: 3552, ...`. We're using SHA2-256, which is rather slow to prove!

A possible optimization is the use of specific "ZK friendly" hash functions. It works great on circuit based arithmetization, allowing direct access to computational units, or (finite) 'field elements'. On zkVM's it is nuanced. Program sees only CPU registers; to overcome it, there are some precompiles which are implemented as circuits -- thus can provide some benefit; but there is still a translation expense between 32-bit integer registers and native field elements. Range checking to detect overflows is not efficient in ZK! There are attempts with ZK friendly hash function precompiles[^4], with limited real-world effect though...


## More on ZK and hash functions

Standardized cryptographic hash algorithms are optimized for the minimal physical chip area. This is NIST's choice. Some others for fast execution on CPU, like the Blake family. They all include lots of operations which are easy on silicon logic like rotations, bitwise operations, etc. These are notoriously slow for ZK provers though. Usually, one bit is represented as a full field element (for example, on BN254 field -- whole 254 bit value per one bit! [^5]). Also, ZK likes linear operations like +, -, and  multiplication. The rest is emulated through those.

There are some newer cryptographic hash functions specifically designed for the ZK efficiency in mind, like Poseidon, Poseidon2, which are already somewhat established but still young; some are better on large fields (Reinforced Concrete), some on smaller (Monolith), while depending on proof system's lookup table support. Some are bleeding edge (Griffin, Anemoi) and super fast. Some are even okay-ish on silicon CPU :) e.g., GMiMC.

These operate on full field elements without translation. Security level is defined by underlying field and instantiation parameters. The smaller the field, the more FEs we need for hash function's state and output. But still, only a few.

So, different zkVM's have different sets of precompiles. Basically all run on RISC-V 32-bit integers. Cairo VM / language provides direct access to the field elements (and invented precompiles), but its VM is so much specialized...


## How fast?

"On my machine" (M1 Min) the proving time of 500 tx batch is 5 minutes. But, SP1 goes like a bulldozer, whatever one throws at it. Supports distributed prover networks and industrial-grade GPUs and proof recursion and whatnot.


## How to avoid the bottleneck?

The setup is quite optimal: proving time depends on the size of addition batch (NOT  batch size times tree capacity). Verification algorithm looks tight.

We need to use ZK friendly hash functions. The framework should provide direct access to native field elements, as used by the arithmetization layer (this excludes zkVMs). The execution trace generation must be super fast (this excludes Cairo 0). The prover must be fast, state of the art is small fields (BabyBear, Mersenne 31 etc), and prover based on FRI, and Circle-STARK: candidates are Plonky3[^6] and STwo[^7]. Better if reasonably mature and modular and open. Leaving us with Plonky3.

And the verification algorithm must be hand-crafted custom AIR circuit.


---
[^1]: https://github.com/unicitynetwork/nd-smt
[^2]: https://github.com/unicitynetwork/whitepaper-tex/releases/download/latest/Unicity.pdf
[^3]: https://docs.succinct.xyz/docs/sp1/introduction
[^4]: https://github.com/Okm165/sp1-poseidon2/pull/8
[^5]: https://github.com/iden3/circomlib/blob/master/circuits/sha256/sha256.circom
[^6]: https://github.com/Plonky3/Plonky3
[^7]: https://github.com/starkware-libs/stwo
