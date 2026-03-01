"""
AI Job Agent - PDF Resume Parser
Extracts text from PDF resumes.
"""

from typing import Dict, Any
import PyPDF2

class PDFResumeParser:
    """Parses text from a PDF resume."""

    def __init__(self):
        self.text_content = ""

    def parse(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text from the PDF file.
        Returns a simplified data structure similar to LaTeX parser.
        """
        self.text_content = ""
        try:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        self.text_content += text + "\n"
        except Exception as e:
            raise RuntimeError(f"Failed to parse PDF: {e}")

        # Return a simple dictionary; PDF structure extraction is hard,
        # so we just return the full text block for the LLM to analyze.
        return {
            "sections": {"content": self.text_content},
            "raw": self.text_content
        }

    def get_text_content(self) -> str:
        """Return the extracted text."""
        return self.text_content
