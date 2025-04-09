import hashlib
import sys
import random
import json

default = 0  # default 'empty' leaf

def hash2(left: int, right:int) -> int:
    # the following assumes that leaf's address/key/hash is bound to leaf's value
    if left == default:
        return right
    elif right == default:
        return left
    else:
        h = hashlib.sha256()
        h.update(left.to_bytes(32, byteorder='big', signed=False))
        h.update(right.to_bytes(32, byteorder='big', signed=False))
        return int.from_bytes(h.digest(), byteorder='big', signed=False)

class SparseMerkleTree:
    def __init__(self, depth=256):
        self.depth = depth
        self.nodes = {}
        self.default = [default] * (depth + 1)
        # Precompute default hashes for each level
        for i in range(1, depth + 1):
            self.default[i] = hash2(self.default[i-1], self.default[i-1])

    def get_root(self):
        return self.get_node(self.depth, '')

    def get_node(self, level, path):
        return self.nodes.get((level, path), self.default[level])

    def update_node(self, level, path, value):
        if level == 0 and not (self.nodes.get((0, path)) is None):
            raise ValueError(f"The leaf '{path}' is already set")
        self.nodes[(level, path)] = value

    def key_to_bits(self, key):
        # Convert key to a string of 'depth' bits
        return format(key, '0{}b'.format(self.depth))

    def insert(self, key, value):
        path = self.key_to_bits(key)
        current = value
        self.update_node(0, path, current)

        for level in range(1, self.depth + 1):
            parent_path = path[:-level] if level < self.depth else ''
            bit = path[-level] if level <= len(path) else '0'

            if bit == '0':
                left = current
                right = self.get_node(level-1, parent_path + '1')
            else:
                left = self.get_node(level-1, parent_path + '0')
                right = current

            current = hash2(left, right)
            self.update_node(level, parent_path, current)
        return current

    def generate_inclusion_proof2(self, key):
        # returns inclusion proof for existing key
        # returns non-inclusion proof for unknown key
        #     that is, the default leaf
        path = self.key_to_bits(key)
        proof = []
        current_path = path

        for level in range(self.depth):
            parent_path = current_path[:-1] if level < self.depth-1 else ''
            last_bit = current_path[-1] if current_path else '0'

            if last_bit == '0':
                sibling_path = parent_path + '1'
            else:
                sibling_path = parent_path + '0'

            sibling_node = self.get_node(level, sibling_path)
            proof.append(sibling_node)
            current_path = parent_path

        return proof

    def generate_inclusion_proof(self, key):
        # compressed proof where a bitmap encodes skipped hashing steps
        path = self.key_to_bits(key)
        chain = []
        bitmap = 0
        current_path = path

        for level in range(self.depth):
            parent_path = current_path[:-1] if level < self.depth-1 else ''
            last_bit = current_path[-1] if current_path else '0'
            sibling_path = parent_path + ('1' if last_bit == '0' else '0')
            sibling_node = self.get_node(level, sibling_path)
            if sibling_node != default:
                bitmap |= (1 << level)
                chain.append(sibling_node)
            current_path = parent_path

        return (bitmap, chain)

    def verify_inclusion_proof(self, key, value, proof):
        path = self.key_to_bits(key)
        current = value
        proof_index = 0
        (bitmap, chain) = proof

        for level in range(self.depth):
            sibling = chain[proof_index] if (bitmap & (1 << level)) else default
            if bitmap & (1 << level):
                proof_index += 1
            bit = path[-level-1] if level < len(path) else '0'
            if bit == '0':
                current = hash2(current, sibling)
            else:
                current = hash2(sibling, current)
        return current

    def generate_non_inclusion_proof(self, key):
        # Same as inclusion proof, since it proves the leaf is 'default'
        return self.generate_inclusion_proof(key)

    def verify_non_inclusion_proof(self, key, proof):
        path = self.key_to_bits(key)
        current = default  # Start with default leaf
        proof_index = 0
        (bitmap, chain) = proof

        for level in range(self.depth):
            sibling = chain[proof_index] if (bitmap & (1 << level)) else default
            if bitmap & (1 << level):
                proof_index += 1
            bit = path[-level-1] if level < len(path) else '0'
            if bit == '0':
                current = hash2(current, sibling)
            else:
                current = hash2(sibling, current)
        return current

    def missing_keys(self, leafpaths):
        # take all chains of siblings
        # make unique
        # remove keys
        # remove prefixes
        def sibling_paths(path):
            paths = []
            current_path = path
            for level in range(self.depth):
                parent_path = current_path[:-1] if level < self.depth-1 else ''
                last_bit = current_path[-1] if current_path else '0'
                sibling_path = parent_path + ('1' if last_bit == '0' else '0')
                paths.append(sibling_path)
                current_path = parent_path
            return paths

        def prefix_free(bitstrings):
            result = set()
            for s in sorted(bitstrings, key=lambda x: (len(x), x)):
                if not any(other.startswith(s) and other != s for other in bitstrings):
                    result.add(s)
            return result

        siblings = [s for leaf in leafpaths for s in sibling_paths(leaf)]
        siblings = set(siblings) - set(leafpaths)
        siblings = prefix_free(siblings)
        return siblings

    def batch_insert(self, keys, values):
        paths = [self.key_to_bits(key) for key in keys]
        uniq_paths = []  # not failing entire batch if there is existing new leaf
        for path, value in zip(paths, values):
            if (0, path) in self.nodes:
                print(f"The leaf '{path}' is already set", file=sys.stderr)
            else:
                uniq_paths.append(path)
                self.nodes[(0, path)] = value

        # Generate proof of consistency
        proof = {}
        for k in self.missing_keys(uniq_paths):
            level = self.depth - len(k)
            if level >= self.depth or level < 0:
                raise ValueError(f"Panic, level {level} out of range")
            v = self.get_node(level, k)
            if v != default:
                proof[k] = v

        # Update higher levels (1 to depth) level by level
        for level in range(1, self.depth + 1):
            # Collect unique prefixes of length (depth - level) from insertion paths
            prefixes = set()
            for path in uniq_paths:
                prefix = path[:self.depth - level]  # First (d - level) bits
                prefixes.add(prefix)

            # Update each affected node at this level
            for prefix in prefixes:
                # Children are at level (l-1) with paths prefix + '0' and prefix + '1'
                left = self.get_node(level - 1, prefix + '0')
                right = self.get_node(level - 1, prefix + '1')
                hash_value = hash2(left, right)
                self.nodes[(level, prefix)] = hash_value

        return proof

    def verify_non_deletion(self, proof, old_root, new_root, keys, values):
        # computing from leaves towards root. This is also important for security: we show that based on leaves
        # we reach a specific root, and intermediate hashes from the proof must not override the chains.
        # Empty batch does not make sense in the security model
        def compute_forest(proof, extra):
            for level in reversed(range(self.depth)):
                extra2 = []
                i = 0
                while i < len(extra):
                    k, kval = extra[i]
                    parent, last_bit = k[:-1], k[-1]
                    sibling = parent + ('1' if last_bit == '0' else '0')
                    if last_bit == '0' and i != len(extra)-1 and extra[i+1][0] == sibling:
                        i = i + 1
                        siblingval = extra[i][1]
                    else:
                        siblingval = proof.get(sibling, default)
                    pv = hash2(kval, siblingval) if last_bit == '0' else hash2(siblingval, kval)
                    extra2.append((parent, pv))
                    i = i + 1
                extra = extra2

            assert len(extra) == 1  # root layer has exactly one node, the root
            return extra[0][1]

        # step 1. compute old root based on proof and 'empty' leaves in place of new batch
        p1 = [(self.key_to_bits(key), default) for key in sorted(keys)]
        r1 = compute_forest(proof, p1)
        if r1 != old_root:
            print(f"Non-deletion proof root mismatch: r:{r1}, oldr:{old_root}", file=sys.stderr)
            return False

        # step 2. compute new root based on proof and leaves from the batch
        p2 = [(self.key_to_bits(key), value) for key, value in sorted(zip(keys, values))]
        r2 = compute_forest(proof, p2)
        if r2 != new_root:
            print(f"Non-deletion proof root mismatch: r:{r2}, newr:{new_root}", file=sys.stderr)
            return False

        # it is possible to compute the root based on
        #   1. empty leaves and the proof - giving the root before batch insertion,
        #   2. leaves in the batch and the proof - giving the root after batch insertion
        #  with the proof content being exactly the same.
        #  Proof is the roots of hash subtrees which did not change during the insertion
        #  thus only the leaves given in the batch did change, everything else is the same
        # and because we explicitly marked the leaves to be added as blank (default) before
        #  the first check, we know that these leaves were blank before inserting the batch,
        #  thus nothing was overwritten
        return True

    def dump_witness2(self, proof, old_root, new_root, keys, values):
        proof2 = [{} for _ in range(self.depth)]  # Pre-initialize with empty dicts
        for k, v in proof.items():
            depth = len(k) - 1
            assert(depth <= self.depth)
            proof2[depth][int(k, 2)] = v
        keys2, values2 = zip(*sorted(zip(keys, values)))

        witness_data = {
            "old_root": old_root,
            "new_root": new_root,
            "keys": keys2,
            "values": values2,
            "proof": proof2,
            "depth": self.depth
        }
        return(json.dumps(witness_data, indent=4))


def main():
    depth = 32

    def to_int(aa):
        if isinstance(aa, (list, tuple)):
            return [to_int(a) for a in aa]
        elif isinstance(aa, bytes):
            return int.from_bytes(aa, byteorder='big')
        else:
            return to_int(str(aa).encode())

    smt = SparseMerkleTree(depth)
    assert smt.get_root() == default
    old_root = default

    keys = []
    values = []
    # first some pre-fillign of the tree
    for i in range(100):
        # ri = random.randint(0, 2**depth-1)
        ri = hash("a"+str(i)) % (2**depth - 1)  # this is python's internal non-cryptographic hash
        if ri in keys:
             break
        keys.append(ri)
        values.append(to_int(("Val " + str(ri)).encode()))

    proof = smt.batch_insert(keys, values)
    new_root = smt.get_root()
    assert smt.verify_non_deletion(proof, old_root, new_root, keys, values)

    keys = []
    values = []
    # this batch goes to proving
    for i in range(50):
        #ri = random.randint(0, 2**depth-1)
        ri = hash("b"+str(i)) % (2**depth - 1)
        if ri in keys:
            break
        keys.append(ri)
        values.append(to_int(("Val " + str(ri)).encode()))

    old_root = new_root
    proof = smt.batch_insert(keys, values)
    new_root = smt.get_root()
    assert smt.verify_non_deletion(proof, old_root, new_root, keys, values)
    print(smt.dump_witness2(proof, old_root, new_root, keys, values))


if __name__ == "__main__":
    main()
