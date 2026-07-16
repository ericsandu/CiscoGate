import json
import re
from typing import List, Tuple, Dict, Any


class TranslationError(Exception):
    """Exception raised when a command cannot be translated."""

    pass


class TranslationTrie:
    def __init__(self, dictionary: Dict[str, Any]):
        """
        Initialize with the root translation dictionary.
        The dictionary should have a "modes" key at the top level.
        """
        self.dictionary = dictionary

        if "modes" not in self.dictionary:
            raise ValueError("Invalid dictionary format: missing 'modes' root key.")

    @classmethod
    def from_json_file(cls, filepath: str) -> "TranslationTrie":
        """Load a TranslationTrie from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            dictionary = json.load(f)
        return cls(dictionary)

    def to_json_file(self, filepath: str) -> None:
        """Export the current TranslationTrie dictionary to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.dictionary, f, indent=2)

    def _get_mode_tree(self, mode: str) -> Dict[str, Any]:
        """Fetch the specific sub-tree for the current operational mode."""
        if mode not in self.dictionary["modes"]:
            raise TranslationError(f"Unknown operational mode: {mode}")
        return self.dictionary["modes"][mode]

    def _check_role_allowed(self, node: Dict[str, Any], role: str) -> bool:
        """Check if the current device role
        is allowed to execute this command."""
        allowed_roles = node.get("_allowed_roles")
        if allowed_roles is None:
            return True  # If not specified, assume allowed for all
        return role in allowed_roles

    def _traverse(
        self,
        tokens: List[str],
        current_node: Dict[str, Any],
        captured_vars: List[str],
        role: str,
    ) -> Dict[str, Any]:
        """
        Recursively traverse the trie based on input tokens.
        Captures dynamic variables marked by <VAR>.
        """
        if not tokens:
            return current_node

        next_token = tokens[0]

        # 1. Exact match attempt
        if next_token in current_node:
            return self._traverse(
                tokens[1:], current_node[next_token], captured_vars, role
            )

        # 2. Variable capture attempt (<VAR>)
        if "<VAR>" in current_node:
            captured_vars.append(next_token)
            return self._traverse(
                tokens[1:], current_node["<VAR>"], captured_vars, role
            )

        # 3. Match failed
        raise TranslationError(
            f"Command token not found in translation dictionary: {next_token}"
        )

    def translate_command(
        self, command: str, current_mode: str, role: str
    ) -> Tuple[str, str]:
        """
        Translates a command string based on the current mode and device role.

        Returns:
            Tuple containing (translated_command, new_mode)
        """
        # Tokenize command (splitting by whitespace)
        tokens = command.strip().split()
        if not tokens:
            raise TranslationError("Empty command")

        mode_tree = self._get_mode_tree(current_mode)
        captured_vars: List[str] = []

        # Traverse the trie
        leaf_node = self._traverse(tokens, mode_tree, captured_vars, role)

        # Ensure we reached a valid translation endpoint
        if (
            "_translate" not in leaf_node
            and "_enters_mode" not in leaf_node
            and "_exits_mode" not in leaf_node
        ):
            raise TranslationError("Incomplete command / Not a valid leaf node.")

        # Check Role Based Access
        if not self._check_role_allowed(leaf_node, role):
            raise TranslationError(f"Command not allowed for device role: {role}")

        # Handle Translation formatting
        translated_cmd = ""
        if "_translate" in leaf_node:
            try:
                translated_cmd = leaf_node["_translate"].format(*captured_vars)
            except IndexError:
                raise TranslationError(
                    "Dictionary mismatch: Not enough variables captured for the translation format string."
                )

        # Determine next state
        new_mode = current_mode
        if "_enters_mode" in leaf_node:
            new_mode = leaf_node["_enters_mode"]
        elif leaf_node.get("_exits_mode") is True:
            # Assuming exits_mode drops back to base 'exec'.
            # In a more advanced implementation, this would pop from a stack.
            new_mode = "exec"

        return translated_cmd, new_mode

    def add_translation(
        self,
        mode: str,
        path: List[str],
        translate_str: str,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """
        Dynamically adds a new translation path to the trie in memory.
        """
        if mode not in self.dictionary["modes"]:
            self.dictionary["modes"][mode] = {}

        current = self.dictionary["modes"][mode]
        for token in path:
            if token not in current:
                current[token] = {}
            current = current[token]

        current["_translate"] = translate_str
        if metadata:
            for k, v in metadata.items():
                current[k] = v

    def add_and_sync_translation(
        self,
        reverse_trie: "TranslationTrie",
        mode: str,
        path: List[str],
        translate_str: str,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """
        Adds a translation to this trie, algorithmically reverses it,
        and injects the reverse mapping into the provided reverse_trie.
        """
        # 1. Add to self
        self.add_translation(mode, path, translate_str, metadata)

        # 2. Reverse the path logic
        rev_path_tokens = translate_str.strip().split()
        reverse_path = []
        for token in rev_path_tokens:
            # Replace format placeholders like {0}, {1} with <VAR>
            if re.match(r"^\{\d+\}$", token):
                reverse_path.append("<VAR>")
            else:
                reverse_path.append(token)

        # 3. Build the reverse translation string from the original path
        rev_translate_tokens = []
        var_index = 0
        for token in path:
            if token == "<VAR>":
                rev_translate_tokens.append(f"{{{var_index}}}")
                var_index += 1
            else:
                rev_translate_tokens.append(token)

        reverse_translate_str = " ".join(rev_translate_tokens)

        # 4. Add the inverted path to the reverse trie
        # (Pass metadata as-is, though complex state changes may require specific handling)
        reverse_trie.add_translation(
            mode, reverse_path, reverse_translate_str, metadata
        )

    def remove_translation(self, mode: str, path: List[str]) -> bool:
        """
        Removes a translation path from the trie and prunes empty branches.
        Returns True if successful, False if the path was not found.
        """
        if mode not in self.dictionary["modes"]:
            return False

        current = self.dictionary["modes"][mode]
        nodes = [(current, None)]  # list of (parent_dict, key_to_reach_child)

        for token in path:
            if token not in current:
                return False
            nodes.append((current[token], token))
            current = current[token]

        # Verify it's a translation endpoint
        if "_translate" not in current:
            return False

        # Remove translation metadata
        current.pop("_translate", None)
        current.pop("_enters_mode", None)
        current.pop("_exits_mode", None)
        current.pop("_allowed_roles", None)

        # Prune empty dictionaries upwards
        for i in range(len(nodes) - 1, 0, -1):
            child_node, key_to_child = nodes[i]
            parent_node, _ = nodes[i - 1]
            if not child_node:  # Dictionary is empty
                del parent_node[key_to_child]
            else:
                break

        return True
