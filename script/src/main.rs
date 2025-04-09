use sp1_sdk::{include_elf, utils, HashableKey, Prover, ProverClient, SP1Stdin};
use std::time::Instant;
use lib::InputData;
use std::fs;
use primitive_types::U256;
use std::process::exit;

const ELF: &[u8] = include_elf!("ndproof-program");


fn main() {
    utils::setup_logger();

    let input_path = "input.json";

    // Read input file
    let json_str = match fs::read_to_string(input_path) {
         Ok(s) => s,
         Err(e) => {
             eprintln!("Error reading file {}: {}", input_path, e);
             exit(1);
         }
     };

    // Parse JSON
    let data: InputData = match serde_json::from_str(&json_str) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("Error parsing JSON from {}: {}", input_path, e);
            exit(1);
        }
    };

    let mut stdin = SP1Stdin::new();
    stdin.write(&data);

    let client = ProverClient::builder().cpu().build(); // ::from_env();

    // dry execution
    let start = Instant::now();
    let (_, report) = client.execute(ELF, &stdin).run().unwrap();
    println!(
        "executed program with {} cycles in {:?}; syscalls: {:?}",
        report.total_instruction_count(),
        start.elapsed(),
        report.syscall_counts
    );

    // Generate the proof
    let start = Instant::now();
    let (pk, vk) = client.setup(ELF);
    // use hash of vk to commit to the program
    println!("verifier client setup in {:?} vk: {}", start.elapsed(), vk.vk.bytes32());

    let start = Instant::now();
    let mut proof = client.prove(&pk, &stdin).core().run().unwrap();
    println!(
        "generated {} proof in {:?}, size {:?} (including public inputs)",
        proof.proof,
        start.elapsed(),
        bincode::serialized_size(&proof).unwrap()
    );

    // Verify proof and public values
    let start = Instant::now();
    client.verify(&proof, &vk).expect("verification failed");
    println!("verified proof in {:?}", start.elapsed());

    // Read and verify the output.
    let h1 = proof.public_values.read::<U256>();
    let h2 = proof.public_values.read::<U256>();
    let n = proof.public_values.read::<u32>();
    println!("Yep, batch with size {} produced state summary transfer from {} to {}.", n, h1, h2);

    // Test a round trip of proof serialization and deserialization.
    // proof.save("proof-with-pis.bin").expect("saving proof failed");
    // let deserialized_proof =
    //     SP1ProofWithPublicValues::load("proof-with-pis.bin").expect("loading proof failed");
    // // Verify the deserialized proof.
    // client.verify(&deserialized_proof, &vk).expect("verification failed");
    // println!("successfully generated and saved and loaded and verified proof for the program!")
}
