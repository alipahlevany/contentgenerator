"""Build empty, email-friendly HTML shells for Melal to fill with existing content."""

import html
import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from contents.core_services.warmup_buttons import BUTTON_LABELS, BUTTON_LABEL_SET


CONTENT_TOKEN = "{{content}}"
UNSUBSCRIBE_TOKEN = "{{unsubscribe}}"
PHOTO_DISPLAY_WIDTH = 400
# Original article destination from the user's selected delivered email.
DEFAULT_LINK_URL = "https://medium.com/ai-advances/algorithms-dont-discriminate-people-do-b779ee074644"

PALETTES = (
    {"background": "#eeefe9", "surface": "#fffefa", "ink": "#243b32", "muted": "#5b6b62", "accent": "#24584a", "soft": "#e7ede5"},
    {"background": "#edf0f4", "surface": "#ffffff", "ink": "#24364d", "muted": "#5d6c7e", "accent": "#284a70", "soft": "#e8eef5"},
    {"background": "#f3ece5", "surface": "#fffdf9", "ink": "#443329", "muted": "#786453", "accent": "#943e2e", "soft": "#f4e7db"},
    {"background": "#efedf2", "surface": "#fffdfd", "ink": "#392e46", "muted": "#716479", "accent": "#59436f", "soft": "#eee8f2"},
    {"background": "#eaf0ef", "surface": "#fcfefd", "ink": "#213e41", "muted": "#567174", "accent": "#1e5d62", "soft": "#e1efec"},
    {"background": "#eeedea", "surface": "#ffffff", "ink": "#30343b", "muted": "#656970", "accent": "#303a48", "soft": "#eceef0"},
)
LAYOUT_NAMES = ("Editorial", "Postcard", "Studio", "Gallery", "After hours", "Letter")

ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "table", "tr", "td", "div", "span", "p", "h1", "a", "img", "br"}


class WarmupTemplateError(ValueError):
    """Raised when an image or email template is unusable."""


def validate_destination_url(url):
    """Validate a click destination without fetching the linked page."""
    try:
        URLValidator(schemes=["https"])(url)
        parts = urlsplit(url)
        if parts.username or parts.password or parts.port is not None or re.search(r"[\s{}<>]", url):
            raise ValueError
        if parts.hostname == "c.mailerever.net":
            raise ValueError
    except (ValidationError, ValueError, TypeError) as exc:
        raise WarmupTemplateError("Use the original HTTPS article URL, without credentials, placeholders, or recipient tracking links.") from exc
    return url


def _photo_link(photo, width, destination_url, radius=0):
    width = min(width, PHOTO_DISPLAY_WIDTH)
    page = html.escape(destination_url, quote=True)
    image = html.escape(photo["image_url"], quote=True)
    alt = html.escape(photo["alt"], quote=True)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="table-layout:fixed;"><tr><td align="center">'
        f'<a href="{page}" target="_blank" style="text-decoration:none;">'
        f'<img src="{image}" alt="{alt}" width="{width}" '
        f'style="display:block;width:{width}px;max-width:100%;height:auto;margin:0 auto;border:0;border-radius:{radius}px;" />'
        '</a></td></tr></table>'
    )


def _content_block(palette, *, inset=False, letter=False):
    background = palette["soft"] if inset else palette["surface"]
    padding = "24px" if inset else "0"
    font = "Georgia,'Times New Roman',serif" if letter else "Arial,Helvetica,sans-serif"
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="table-layout:fixed;background:{background};"><tr>'
        f'<td bgcolor="{background}" style="padding:{padding};border-radius:8px;'
        f'color:{palette["ink"]};font-family:{font};font-size:{17 if letter else 16}px;line-height:1.85;text-align:left;'
        f'overflow-wrap:anywhere;word-break:break-word;">{CONTENT_TOKEN}</td>'
        '</tr></table>'
    )


def _button(palette, destination_url, label):
    page = html.escape(destination_url, quote=True)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'align="center" style="margin:0 auto;"><tr><td bgcolor="{palette["accent"]}" '
        f'style="border:1px solid {palette["accent"]};border-radius:4px;background:{palette["accent"]};mso-padding-alt:15px 24px;">'
        f'<a href="{page}" target="_blank" style="display:inline-block;box-sizing:border-box;max-width:100%;padding:15px 24px;white-space:normal;overflow-wrap:break-word;text-align:center;'
        f'color:{palette.get("button_ink", "#ffffff")};font-size:13px;line-height:20px;font-weight:700;text-decoration:none;">{html.escape(label)}&nbsp;&nbsp;&rarr;</a>'
        '</td></tr></table>'
    )


def render_warmup_html(photo, run_date, sequence, destination_url=DEFAULT_LINK_URL, *, button_label=None):
    """Render a designed shell: Melal owns the entire email message."""
    if button_label is None:
        button_label = BUTTON_LABELS[(run_date.toordinal() + sequence) % len(BUTTON_LABELS)]
    if button_label not in BUTTON_LABEL_SET:
        raise WarmupTemplateError("Choose a button label from the English catalogue.")
    seed = hashlib.sha256(f"{run_date.isoformat()}:{sequence}:palette".encode()).digest()[0]
    palette = PALETTES[seed % len(PALETTES)]
    variation = (run_date.toordinal() + sequence) % len(LAYOUT_NAMES)
    validate_destination_url(destination_url)
    if variation == 4:
        palette = {**palette, "surface": palette["ink"], "ink": "#f7f9f8",
                   "muted": "#d2dcd7", "accent": palette["soft"],
                   "soft": "#53615f", "button_ink": palette["ink"]}
    message = _content_block(palette, inset=variation == 2, letter=variation == 5)
    if variation == 0:
        body_rows = (
            f'<tr><td>{_photo_link(photo, 600, destination_url)}</td></tr>'
            f'<tr><td class="warmup-pad" style="padding:36px 40px 28px;">{message}</td></tr>'
        )
    elif variation == 1:
        body_rows = (
            f'<tr><td style="padding:20px 20px 0;">{_photo_link(photo, 560, destination_url, 12)}</td></tr>'
            f'<tr><td class="warmup-pad" style="padding:32px 48px 28px;">{message}</td></tr>'
        )
    elif variation == 2:
        body_rows = (
            f'<tr><td bgcolor="{palette["soft"]}" style="padding:24px 24px 24px 0;background:{palette["soft"]};border-right:12px solid {palette["accent"]};">'
            f'{_photo_link(photo, 564, destination_url)}</td></tr>'
            f'<tr><td class="warmup-pad" style="padding:28px 28px;">{message}</td></tr>'
        )
    elif variation == 3:
        body_rows = (
            f'<tr><td bgcolor="{palette["soft"]}" style="padding:24px;background:{palette["soft"]};">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="table-layout:fixed;background:#ffffff;">'
            f'<tr><td style="padding:12px;">{_photo_link(photo, 528, destination_url)}</td></tr>'
            '</table></td></tr>'
            f'<tr><td class="warmup-pad" style="padding:36px 40px 28px;">{message}</td></tr>'
        )
    elif variation == 4:
        body_rows = (
            f'<tr><td style="padding:20px;">{_photo_link(photo, 560, destination_url, 2)}</td></tr>'
            f'<tr><td class="warmup-pad" style="padding:12px 40px 28px;">{message}</td></tr>'
        )
    else:
        body_rows = (
            f'<tr><td class="warmup-pad" style="padding:40px 48px 30px;">{message}</td></tr>'
            f'<tr><td class="warmup-pad" style="padding:0 48px 28px;">{_photo_link(photo, 504, destination_url, 2)}</td></tr>'
        )

    photographer = html.escape(photo["photographer"])
    credit_source = html.escape(photo.get("credit_source", "Pexels"))
    return (
        '<!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        '<meta name="x-apple-disable-message-reformatting" />'
        '<title>Email template</title>'
        '<style>table{border-collapse:separate;border-spacing:0;mso-table-lspace:0pt;mso-table-rspace:0pt}'
        '@media only screen and (max-width:620px){'
        '.warmup-shell{width:100%!important;max-width:100%!important}'
        '.warmup-pad{padding-left:20px!important;padding-right:20px!important}'
        '.warmup-outer{padding:16px 8px!important}'
        '}</style></head>'
        f'<body style="margin:0;padding:0;background:{palette["background"]};font-family:Arial,Helvetica,sans-serif;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{palette["background"]};"><tr><td class="warmup-outer" align="center" style="padding:32px 12px;">'
        '<table role="presentation" class="warmup-shell" width="600" cellpadding="0" '
        f'cellspacing="0" border="0" bgcolor="{palette["surface"]}" style="width:600px;max-width:600px;table-layout:fixed;background:{palette["surface"]};'
        f'border:1px solid {palette["soft"]};border-radius:{16 if variation == 1 else 4}px;">'
        f'<tr><td height="3" bgcolor="{palette["accent"]}" style="height:3px;line-height:3px;'
        f'font-size:0;background:{palette["accent"]};">&nbsp;</td></tr>'
        f'{body_rows}'
        f'<tr><td class="warmup-pad" align="center" style="padding:0 40px 36px;">{_button(palette, destination_url, button_label)}</td></tr>'
        f'<tr><td class="warmup-pad" style="padding:22px 40px;border-top:1px solid {palette["soft"]};'
        f'color:{palette["muted"]};font-size:11px;line-height:1.9;text-align:center;">'
        f'Photo by {photographer} on {credit_source}'
        f'<br />{UNSUBSCRIBE_TOKEN}'
        '</td></tr></table></td></tr></table></body></html>'
    )


class _EmailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = set()
        self.images = []
        self.links = []
        self.in_body = False
        self.content_slots = 0
        self.unsubscribe_slots = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            raise WarmupTemplateError(f"Unsupported email tag: {tag}.")
        self.tags.add(tag)
        if tag == "body":
            self.in_body = True
        values = {}
        for name, value in attrs:
            name = name.lower()
            if any(token in (value or "") for token in (CONTENT_TOKEN, UNSUBSCRIBE_TOKEN)):
                raise WarmupTemplateError("Melal placeholders must be body content, not HTML attributes.")
            if name.startswith("on") or name in {"srcset", "background", "formaction", "ping", "http-equiv"}:
                raise WarmupTemplateError("HTML contains an unsafe attribute.")
            if name in {"href", "src"} and tag not in {"a", "img"}:
                raise WarmupTemplateError("HTML contains an unexpected URL attribute.")
            values[name] = value
        if tag == "img":
            self.images.append((values.get("src") or "").strip())
        if tag == "a":
            self.links.append((values.get("href") or "").strip())

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag == "body":
            self.in_body = False

    def handle_data(self, data):
        if self.in_body:
            self.content_slots += data.count(CONTENT_TOKEN)
            self.unsubscribe_slots += data.count(UNSUBSCRIBE_TOKEN)


def _has_host(url, hostname):
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.hostname == hostname
            and not parts.username
            and not parts.password
            and parts.port is None
        )
    except ValueError:
        return False


def validate_warmup_html(markup, photo=None, destination_url=None):
    """Validate generated or manually edited HTML before it is saved."""
    markup = (markup or "").strip()
    if len(markup) > 80_000 or not markup.lower().startswith("<!doctype html"):
        raise WarmupTemplateError("Template needs a compact HTML doctype document.")
    if markup.count(CONTENT_TOKEN) != 1 or markup.count(UNSUBSCRIBE_TOKEN) != 1:
        raise WarmupTemplateError("Template needs one content and one unsubscribe placeholder.")
    if re.search(r"javascript:|data:|@import\b|url\s*\(|expression\s*\(", markup, re.IGNORECASE):
        raise WarmupTemplateError("Template contains unsupported HTML or CSS.")

    parser = _EmailParser()
    try:
        parser.feed(markup)
        parser.close()
    except WarmupTemplateError:
        raise
    except Exception as exc:
        raise WarmupTemplateError("Template HTML could not be parsed.") from exc
    if not {"html", "head", "body", "table", "img", "a"}.issubset(parser.tags) or "</html>" not in markup.lower():
        raise WarmupTemplateError("Template is missing its email document structure.")
    if len(parser.images) != 1:
        raise WarmupTemplateError("Template needs one externally hosted photo.")
    image_url = parser.images[0]
    is_pexels = _has_host(image_url, "images.pexels.com")
    is_picsum = bool(re.fullmatch(r"https://picsum\.photos/id/\d{1,8}/1200/800\.jpg", image_url))
    if not (is_pexels or is_picsum):
        raise WarmupTemplateError("Template photo URL is not from an approved source.")
    if parser.content_slots != 1 or parser.unsubscribe_slots != 1:
        raise WarmupTemplateError("Melal needs content and unsubscribe placeholders in the email body.")
    if len(parser.links) not in (2, 3):
        raise WarmupTemplateError("Image and button links are required.")
    action_links = parser.links[:2]
    if action_links[0] != action_links[1]:
        raise WarmupTemplateError("Image and button must use the same destination URL.")
    validate_destination_url(action_links[0])
    if destination_url is not None and action_links[0] != destination_url:
        raise WarmupTemplateError("Template changed the configured destination URL.")
    # Previously saved templates may still have their original credit link.
    # New templates render this attribution as plain, non-clickable text.
    if len(parser.links) == 3:
        credit_link = parser.links[2]
        page_host = "www.pexels.com" if is_pexels else "unsplash.com"
        if (not _has_host(credit_link, page_host)
                or (is_picsum and not credit_link.startswith("https://unsplash.com/photos/"))):
            raise WarmupTemplateError("Photo credit must lead to the selected source's photo page.")
        if photo and credit_link != photo["photo_page"]:
            raise WarmupTemplateError("Template changed the selected photo credit.")
    if photo:
        if parser.images[0] != photo["image_url"]:
            raise WarmupTemplateError("Template changed the selected photo.")
        if len(parser.links) == 2:
            credit = f"Photo by {html.escape(photo['photographer'])} on {html.escape(photo.get('credit_source', 'Pexels'))}"
            if credit not in markup:
                raise WarmupTemplateError("Template must retain the photo attribution text.")
    return markup
