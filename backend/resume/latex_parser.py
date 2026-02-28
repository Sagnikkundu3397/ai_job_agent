"""
AI Job Agent - LaTeX Resume Parser
Parses Jake's Resume LaTeX template, extracting and preserving structure.
"""

import re
from pathlib import Path
from typing import Optional


class LaTeXResumeParser:
    """
    Parses Jake's Resume LaTeX template.
    Extracts content sections while preserving the template structure exactly.
    """

    # Regex patterns for Jake's Resume commands
    PATTERNS = {
        "section": re.compile(r"\\resumeSubHeadingListStart(.*?)\\resumeSubHeadingListEnd", re.DOTALL),
        "subheading": re.compile(
            r"\\resumeSubheading\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}",
            re.DOTALL,
        ),
        "project_heading": re.compile(
            r"\\resumeProjectHeading\s*\{([^}]*)\}\s*\{([^}]*)\}",
            re.DOTALL,
        ),
        "item": re.compile(r"\\resumeItem\{([^}]*)\}", re.DOTALL),
        "sub_item": re.compile(r"\\resumeSubItem\{([^}]*)\}", re.DOTALL),
        "section_header": re.compile(r"\\section\{([^}]*)\}"),
        "skill_item": re.compile(
            r"\\textbf\{([^}]*)\}\{:\s*([^}]*)\}|\\textbf\{([^}]*)\}:\s*(.+?)(?=\\\\|$)",
            re.DOTALL,
        ),
    }

    def __init__(self):
        self.raw_content = ""
        self.preamble = ""
        self.body = ""
        self.sections = {}
        self.section_order = []

    def parse(self, filepath: str) -> dict:
        """
        Parse a Jake's Resume .tex file.

        Returns:
            dict with keys: 'preamble', 'sections', 'section_order', 'raw'
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {filepath}")

        self.raw_content = path.read_text(encoding="utf-8")
        self._split_preamble_body()
        self._extract_sections()

        return {
            "preamble": self.preamble,
            "sections": self.sections,
            "section_order": self.section_order,
            "raw": self.raw_content,
        }

    def _split_preamble_body(self):
        """Split the LaTeX content into preamble and body."""
        begin_match = re.search(r"\\begin\{document\}", self.raw_content)
        end_match = re.search(r"\\end\{document\}", self.raw_content)

        if begin_match and end_match:
            self.preamble = self.raw_content[: begin_match.end()]
            self.body = self.raw_content[begin_match.end() : end_match.start()]
        else:
            self.preamble = ""
            self.body = self.raw_content

    def _extract_sections(self):
        """Extract all sections from the document body."""
        # Find all \section{...} headers
        section_headers = list(self.PATTERNS["section_header"].finditer(self.body))

        for i, match in enumerate(section_headers):
            section_name = match.group(1).strip()
            self.section_order.append(section_name)

            # Get content between this section and the next
            start = match.end()
            end = section_headers[i + 1].start() if i + 1 < len(section_headers) else len(self.body)
            section_content = self.body[start:end].strip()

            # Parse section content based on type
            self.sections[section_name] = self._parse_section_content(
                section_name, section_content
            )

    def _parse_section_content(self, section_name: str, content: str) -> dict:
        """Parse the content of a section into structured data."""
        section_data = {
            "raw": content,
            "items": [],
        }

        name_lower = section_name.lower()

        if "skill" in name_lower:
            section_data["type"] = "skills"
            section_data["items"] = self._parse_skills(content)
        elif "education" in name_lower:
            section_data["type"] = "education"
            section_data["items"] = self._parse_subheadings(content)
        elif "experience" in name_lower:
            section_data["type"] = "experience"
            section_data["items"] = self._parse_subheadings(content)
        elif "project" in name_lower:
            section_data["type"] = "projects"
            section_data["items"] = self._parse_projects(content)
        else:
            section_data["type"] = "generic"
            section_data["items"] = self._parse_subheadings(content)

        return section_data

    def _parse_subheadings(self, content: str) -> list:
        """Parse resumeSubheading entries with their bullet items."""
        items = []
        for match in self.PATTERNS["subheading"].finditer(content):
            heading = {
                "field1": match.group(1).strip(),
                "field2": match.group(2).strip(),
                "field3": match.group(3).strip(),
                "field4": match.group(4).strip(),
                "bullets": [],
            }

            # Find bullet items after this subheading
            after_heading = content[match.end():]
            next_heading = self.PATTERNS["subheading"].search(after_heading)
            if next_heading:
                after_heading = after_heading[:next_heading.start()]

            for item_match in self.PATTERNS["item"].finditer(after_heading):
                heading["bullets"].append(item_match.group(1).strip())

            items.append(heading)

        return items

    def _parse_projects(self, content: str) -> list:
        """Parse project heading entries."""
        items = []
        for match in self.PATTERNS["project_heading"].finditer(content):
            project = {
                "title_tech": match.group(1).strip(),
                "date": match.group(2).strip(),
                "bullets": [],
            }

            # Find bullet items after this project
            after_project = content[match.end():]
            next_project = self.PATTERNS["project_heading"].search(after_project)
            if next_project:
                after_project = after_project[:next_project.start()]

            for item_match in self.PATTERNS["item"].finditer(after_project):
                project["bullets"].append(item_match.group(1).strip())

            items.append(project)

        return items

    def _parse_skills(self, content: str) -> list:
        """Parse Technical Skills section."""
        items = []
        # Match patterns like \textbf{Languages}: Java, Python, ...
        skill_pattern = re.compile(
            r"\\textbf\{([^}]+)\}[:\s]*\s*(.+?)(?=\\\\|\\resumeSubHeadingListEnd|$)",
            re.DOTALL,
        )
        for match in skill_pattern.finditer(content):
            items.append({
                "category": match.group(1).strip(),
                "skills": match.group(2).strip().rstrip("\\").strip(),
            })
        return items

    def get_text_content(self) -> str:
        """Get all text content from the resume (for AI analysis)."""
        text_parts = []
        for section_name in self.section_order:
            section = self.sections.get(section_name, {})
            text_parts.append(f"\n=== {section_name} ===")

            for item in section.get("items", []):
                if section["type"] == "skills":
                    text_parts.append(f"{item['category']}: {item['skills']}")
                elif section["type"] == "projects":
                    text_parts.append(f"\n{item.get('title_tech', '')}")
                    for bullet in item.get("bullets", []):
                        text_parts.append(f"  - {bullet}")
                else:
                    text_parts.append(
                        f"\n{item.get('field1', '')} | {item.get('field3', '')}"
                    )
                    text_parts.append(
                        f"  {item.get('field2', '')} | {item.get('field4', '')}"
                    )
                    for bullet in item.get("bullets", []):
                        text_parts.append(f"  - {bullet}")

        return "\n".join(text_parts)


# Singleton
latex_parser = LaTeXResumeParser()
