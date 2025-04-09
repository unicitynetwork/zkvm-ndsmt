use serde::{Deserialize, Serialize};
use primitive_types::U256;
use std::collections::HashMap;

#[derive(Serialize, Deserialize, Debug)]
pub struct InputData {
    #[serde(deserialize_with = "deserialize_u256")]
    pub old_root: U256,
    #[serde(deserialize_with = "deserialize_u256")]
    pub new_root: U256,
    pub keys: Vec<u32>,
    #[serde(deserialize_with = "deserialize_vec_u256")]
    pub values: Vec<U256>,
    #[serde(deserialize_with = "deserialize_proof")]
    pub proof: Vec<HashMap<u32, U256>>,
    pub depth: u32,
}

// same, not JSON version
#[derive(Serialize, Deserialize, Debug)]
pub struct InputData2 {
    pub old_root: U256,
    pub new_root: U256,
    pub keys: Vec<u32>,
    pub values: Vec<U256>,
    pub proof: Vec<HashMap<u32, U256>>,
    pub depth: u32,
}

// Custom deserializer for U256 from JSON numbers (not strings)
fn deserialize_u256<'de, D>(deserializer: D) -> Result<U256, D::Error>
where
    D: serde::Deserializer<'de>,
{
    // First deserialize to serde_json::Number using arbitrary precision
    let num = serde_json::Number::deserialize(deserializer)?;
    // Convert to string and parse to U256
    U256::from_dec_str(&num.to_string())
        .map_err(serde::de::Error::custom)
}

// Custom deserializer for Vec<U256>
fn deserialize_vec_u256<'de, D>(deserializer: D) -> Result<Vec<U256>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let numbers: Vec<serde_json::Number> = Vec::deserialize(deserializer)?;
    numbers
        .into_iter()
        .map(|n| U256::from_dec_str(&n.to_string()).map_err(serde::de::Error::custom))
        .collect()
}

// Custom deserializer for proof with number preservation
fn deserialize_proof<'de, D>(deserializer: D) -> Result<Vec<HashMap<u32, U256>>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let vec_of_maps: Vec<HashMap<String, serde_json::Number>> = Vec::deserialize(deserializer)?;

    vec_of_maps
        .into_iter()
        .map(|string_map| {
            string_map
                .into_iter()
                .map(|(k_str, num)| {
                    // Parse key from string to u32
                    let key = k_str.parse::<u32>()
                        .map_err(serde::de::Error::custom)?;

                    // Parse value from JSON number to U256
                    let value = U256::from_dec_str(&num.to_string())
                        .map_err(serde::de::Error::custom)?;

                    Ok((key, value))
                })
                .collect::<Result<HashMap<u32, U256>, _>>()
        })
        .collect::<Result<Vec<HashMap<u32, U256>>, _>>()
}

