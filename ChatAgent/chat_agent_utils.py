import textwrap


def flat_system_prompt_sections(sections: dict) -> str:
    parts = []

    def clean_text(val: str) -> str:
        # remove common indentation + strip edges
        return textwrap.dedent(val).strip()

    def recurse(d):
        for key, value in d.items():
            header = f"{key.upper()}:"

            if isinstance(value, dict):
                parts.append(header)
                recurse(value)

            elif isinstance(value, (list, set)):
                items = [clean_text(str(v)) for v in value if str(v).strip()]
                if items:
                    parts.append(header)
                    parts.append("\n".join(items))

            else:
                val = clean_text(str(value))
                if val:
                    parts.append(header)
                    parts.append(val)

    recurse(sections)

    return "\n\n".join(parts)
