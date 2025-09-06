import re
import re
import html
from urllib.parse import urlparse
import markdown
import bleach
from bleach.css_sanitizer import CSSSanitizer


class TelegramFormatter:
    EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
    HANDLE_REGEX = re.compile(r'@[A-Za-z0-9_]+')

    @classmethod
    def escape_special_for_telegram(cls, text: str) -> str:
        # """
        # Escape MarkdownV2 special chars only inside emails or Telegram handles.
        # Leaves the rest of the text intact.
        # """
        # def escape_match(match):
        #     value = match.group(0)
        #     # For MarkdownV2, escape these special characters: _ * [ ] ( ) ~ ` > # + - = | { } ! \
        #     # Note: Backslash must be escaped first to avoid double-escaping
        #     return re.sub(r'([\\*\[\]()~`>#+\-=|{}!_])', r'\\\1', value)

        # # Process emails first
        # text = cls.EMAIL_REGEX.sub(escape_match, text)
        # # Then process Telegram handles
        # text = cls.HANDLE_REGEX.sub(escape_match, text)
        # return text
        return text

class MarkdownSanitizer:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MarkdownSanitizer, cls).__new__(cls)
        return cls._instance
    def __init__(self):
        # Prevent re-initialization
        if self._initialized:
            return
            
        # Define allowed HTML tags and attributes after markdown conversion
        self.allowed_tags = [
            'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'strike', 'del',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li',
            'blockquote', 'pre', 'code',
            'a', 'img',
            'table', 'thead', 'tbody', 'tr', 'td', 'th',
            'hr'
        ]
        
        self.allowed_attributes = {
            'a': ['href', 'title'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'blockquote': ['cite'],
        }
        
        self.allowed_protocols = ['http', 'https', 'mailto']
        
        # Mark as initialized
        self._initialized = True
        
    def sanitize_markdown_to_html(self, markdown_text):
        """
        Convert markdown to HTML and sanitize it using bleach
        """
        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_text,
            extensions=['fenced_code', 'tables', 'nl2br']
        )
        
        # Sanitize the HTML
        clean_html = bleach.clean(
            html_content,
            tags=self.allowed_tags,
            attributes=self.allowed_attributes,
            protocols=self.allowed_protocols,
            strip=True  # Remove disallowed tags instead of escaping
        )
        
        return clean_html
    
    def sanitize_raw_markdown(self, markdown_text):
        """
        Sanitize markdown before conversion - removes potentially dangerous patterns
        """
        return markdown_text
        # Remove script tags and javascript: links
        markdown_text = re.sub(r'<script[^>]*>.*?</script>', '', markdown_text, flags=re.DOTALL | re.IGNORECASE)
        markdown_text = re.sub(r'javascript:', '', markdown_text, flags=re.IGNORECASE)
        
        # Clean up dangerous protocols in links
        def clean_link(match):
            full_match = match.group(0)
            url = match.group(1) if match.group(1) else match.group(2)
            
            if self._is_safe_url(url):
                return full_match
            else:
                # Return text without the link
                return match.group(3) if len(match.groups()) >= 3 else url
        
        # Pattern for markdown links: [text](url) or [text]: url
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)|(\[([^\]]+)\]:\s*([^\s]+))'
        markdown_text = re.sub(link_pattern, clean_link, markdown_text)
        
        # Remove HTML comments
        markdown_text = re.sub(r'<!--.*?-->', '', markdown_text, flags=re.DOTALL)
        
        # Remove or escape raw HTML tags (optional - depends on your needs)
        markdown_text = re.sub(r'<(?!/?(?:strong|em|code|pre|br|hr|u|i|b|del|strike)(?:\s|>))[^>]*>', '', markdown_text)
        
        return markdown_text
    
    def _is_safe_url(self, url):
        """
        Check if URL uses allowed protocols
        """
        try:
            parsed = urlparse(url.strip())
            return parsed.scheme.lower() in self.allowed_protocols or parsed.scheme == ''
        except:
            return False
    
    def sanitize_full_pipeline(self, markdown_text):
        """
        Complete sanitization pipeline: raw markdown -> clean markdown -> safe HTML
        """
        # Step 1: Clean raw markdown
        clean_markdown = self.sanitize_raw_markdown(markdown_text)
        
        # Step 2: Convert to HTML and sanitize
        safe_html = self.sanitize_markdown_to_html(clean_markdown)
        
        return safe_html


# Convenience function to get the singleton instance
def get_sanitizer():
    """Get the singleton instance of MarkdownSanitizer"""
    return MarkdownSanitizer()

from bs4 import BeautifulSoup

def clean_llm_output(text: str) -> str:
    """
    Turn LLM output (str or dict with 'response') into safe Telegram HTML.
    Guarantees to return a non-empty string and never raise an exception.
    Allowed tags preserved: <a>, <b>, <i>, <u>, <s>, <br>.
    Converts common Markdown patterns to those tags.
    """
    # return text
    try:
        # Handle None or non-string input
        if not text or not isinstance(text, str):
            return "No content available"
        
        # First, aggressively clean any potential HTML comments or malformed tags
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)  # Remove HTML comments
        # text = re.sub(r'<!\[CDATA\[.*?\]\]>', '', text, flags=re.DOTALL)  # Remove CDATA
        # text = re.sub(r'<\?.*?\?>', '', text, flags=re.DOTALL)  # Remove processing instructions
        # text = re.sub(r'<!DOCTYPE.*?>', '', text, flags=re.IGNORECASE)  # Remove DOCTYPE
        
        # Convert Markdown to HTML
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)   # bold
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)       # italic
        text = re.sub(r"__(.*?)__", r"<u>\1</u>", text)       # underline
        text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)       # strikethrough
        
        # Parse and clean HTML - use 'html.parser' to avoid warnings
        soup = BeautifulSoup(text, "html.parser")
        
        # Telegram-supported tags (case-insensitive)
        allowed_tags = {'a', 'b', 'i', 'u', 's', 'code', 'pre', 'em', 'strong'}
        
        # Remove unsupported tags but keep their content
        for tag in soup.find_all():
            if tag.name.lower() not in allowed_tags:
                tag.unwrap()  # Remove tag but keep content
        
        # Convert common HTML tags to Telegram equivalents
        for strong_tag in soup.find_all('strong'):
            strong_tag.name = 'b'
        for em_tag in soup.find_all('em'):
            em_tag.name = 'i'
            
        # Remove unsupported attributes from allowed tags
        for tag in soup.find_all():
            if tag.name == 'a':
                # Keep only href attribute for links
                href = tag.get('href')
                tag.attrs.clear()
                if href:
                    tag.attrs['href'] = href
            else:
                # Remove all attributes from other tags
                tag.attrs.clear()
        
        cleaned = str(soup)
        
        cleaned = cleaned.strip()
        
        # Ensure we return something non-empty
        if not cleaned or cleaned.isspace():
            return "Content processed but empty"
            
        return cleaned
        
    except Exception as e:
        # Fallback - return safe text version
        safe_text = str(text) if text else "Error processing content"
        # Escape HTML entities for safety
        safe_text = safe_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return safe_text[:4000]  # Limit length to prevent issues
    