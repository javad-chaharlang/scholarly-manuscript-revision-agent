'''Isolated, static CSS enhancements for the Streamlit shell.'''

from __future__ import annotations

import streamlit as st


_BASE_CSS = '''
<style>
.stApp { overflow-x: clip; }
.stMainBlockContainer { max-width: 1500px; padding-top: 1.25rem; padding-bottom: 2rem; }
.st-key-srs_product_bar { border: 1px solid rgba(100,116,139,.20); border-radius: 14px;
  padding: .6rem .8rem; box-shadow: 0 4px 16px rgba(15,23,42,.06); }
.st-key-srs_context_bar, .st-key-srs_welcome_hero { border-radius: 14px; padding: .45rem .65rem;
  box-shadow: 0 4px 16px rgba(15,23,42,.06); }
.st-key-srs_stepper { border-radius: 12px; padding: .35rem; overflow: visible; }
.st-key-srs_stepper button, .st-key-srs_stepper a {
  min-height: 2.75rem; white-space: normal; font-size: .92rem; line-height: 1.2;
}
.st-key-srs_quick_actions button, .st-key-srs_action_row button { min-height: 2.65rem; }
.st-key-srs_hero_actions button { min-height: 2.8rem; }
[data-testid='stNavigation'] a { border-radius: 8px; font-size: .96rem; font-weight: 500; }
[data-testid='stNavigation'] a:hover { background: rgba(79,70,229,.09); }
[data-testid='stNavigation'] a:focus-visible, button:focus-visible, a:focus-visible {
  outline: 3px solid rgba(37,99,235,.45); outline-offset: 2px;
}
.st-key-srs_blocker { border-inline-start: 5px solid #DC2626; }
.st-key-srs_warning { border-inline-start: 5px solid #D97706; }
.st-key-srs_success { border-inline-start: 5px solid #059669; }
.st-key-srs_info { border-inline-start: 5px solid #2563EB; }
.st-key-srs_exact_comment textarea { font-family: ui-serif, Georgia, serif; }
@media (max-width: 900px) {
  .stMainBlockContainer { padding-inline: 1rem; padding-top: .75rem; }
  .st-key-srs_product_bar, .st-key-srs_context_bar,
  .st-key-srs_welcome_hero { padding: .35rem .45rem; }
  .st-key-srs_stepper button { min-height: 3rem; }
  [data-testid='stNavigation'] a { font-size: .92rem; }
}
</style>
'''

_RTL_CSS = '''
<style>
.stApp .main { direction: rtl; }
.stApp .main input, .stApp .main textarea, .stApp .main [data-testid="stDataFrame"] { direction: ltr; text-align: left; }
.stApp .main .stMarkdown, .stApp .main label, .stApp .main button { text-align: right; }
</style>
'''

_RTL_ENHANCEMENT_CSS = '''
<style>
[data-testid='stSidebar'], [data-testid='stNavigation'] { direction: rtl; }
[data-testid='stSidebar'] .stMarkdown,
[data-testid='stSidebar'] label { text-align: right; }
.stApp .main input, .stApp .main textarea,
.stApp .main [data-testid='stDataFrame'] {
  direction: inherit; unicode-bidi: plaintext; text-align: start;
}
.stApp code { direction: ltr; unicode-bidi: isolate; }
</style>
'''


def apply_theme(*, rtl: bool = False) -> None:
    st.html(_BASE_CSS)
    if rtl:
        st.html(_RTL_CSS)
        st.html(_RTL_ENHANCEMENT_CSS)
