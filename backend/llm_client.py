import json
import os

from openai import OpenAI
from translation_trie import TranslationTrie

# Initialize OpenAI Client using environment variable placeholder
# Expects OPENAI_API_KEY to be set in the environment before running the server.
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE"))


def translate_and_learn_command(
    command: str,
    source_os: str,
    target_os: str,
    role: str,
    current_mode: str,
    forward_trie: TranslationTrie,
    reverse_trie: TranslationTrie,
) -> str:
    """
    Prompts OpenAI to translate an unknown command, injects the new knowledge
    into both dictionaries dynamically, and returns the translated string.
    """

    prompt = f"""
    You are an expert network engineer. 
    Translate the following {source_os} command template to {target_os}. 
    The device role is {role} and the current operational mode is '{current_mode}'. 
    
    Command Template to translate: '{command}'
    
    Note: The command has already been sanitized for Zero-Knowledge Translation. 
    Sensitive variables like IP addresses, interfaces, or names have been replaced with the exact string '<VAR>'.
    
    Identify the mapping and output the following exact JSON schema:
    {{
        "source_path": ["list", "of", "original", "template", "words", "preserving", "the", "exact", "<VAR>", "tokens"],
        "target_translate_str": "The translated template with variables replaced by {{0}}, {{1}} format placeholders.",
        "new_mode": "Optional: the new operational mode if this command changes it, otherwise omit."
    }}
    
    Example input (Cisco to Fortinet): 'ip address <VAR> <VAR>'
    Example JSON output:
    {{
        "source_path": ["ip", "address", "<VAR>", "<VAR>"],
        "target_translate_str": "set ip {{0}} {{1}}"
    }}
    
    Return ONLY valid JSON.
    """

    # Query OpenAI (gpt-4o) with forced JSON output
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are a network translation assistant designed to output strict JSON schemas.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )

    try:
        raw_text = response.choices[0].message.content
        mapping = json.loads(raw_text)

        path = mapping.get("source_path")
        translate_str = mapping.get("target_translate_str")
        metadata = {}

        if "new_mode" in mapping:
            metadata["_enters_mode"] = mapping["new_mode"]

        if not path or not translate_str:
            raise ValueError("LLM returned incomplete JSON mapping.")

        # 1. Update the Dual-Tree in memory (Algorithmically Reverses the Translation)
        forward_trie.add_and_sync_translation(
            reverse_trie=reverse_trie,
            mode=current_mode,
            path=path,
            translate_str=translate_str,
            metadata=metadata,
        )

        # 2. Perform the actual translation on the user's raw string
        # now that the trie knows it. This captures the variables seamlessly.
        translated_cmd, _ = forward_trie.translate_command(command, current_mode, role)

        return translated_cmd

    except json.JSONDecodeError:
        raise Exception(f"Failed to parse LLM response as JSON. Response: {raw_text}")
    except Exception as e:
        raise Exception(f"LLM Translation integration failed: {str(e)}")
