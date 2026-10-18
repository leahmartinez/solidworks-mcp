"""Apply the house style to document defaults and to every annotation outside the title block."""
from __future__ import annotations

from .. import com
from .context import DrawingContext
from .views import ANN_NOTE

MAX_TEXT_PREF_ID = 60   # swUserPreferenceTextFormat_e ids are well below this


def capture_sheet_text(ctx: DrawingContext):
    """Remember font, height and bold of every sheet-level note (title block)."""
    saved = []
    sheet = com.views(ctx.dwg)[0]
    for n in com.notes(sheet):
        try:
            ann = com.call(n, "GetAnnotation")
            tf = ann.GetTextFormat(0)
            saved.append((ann, str(tf.TypeFaceName), float(tf.CharHeight), bool(tf.Bold)))
        except Exception:
            continue
    return saved


def restore_sheet_text(saved) -> int:
    n = 0
    for ann, face, height, bold in saved:
        try:
            tf = ann.GetTextFormat(0)
            tf.TypeFaceName, tf.CharHeight, tf.Bold = face, height, bold
            ann.SetTextFormat(0, False, tf)
            n += 1
        except Exception:
            continue
    return n


def apply_house_style(ctx: DrawingContext) -> str:
    """Typeface everywhere; dimension height for dims/GD&T, label height for view labels,
    note height (pt) for notes.

    Changing the document text defaults also resizes title-block notes, so their format is
    captured first and restored afterwards.
    """
    st = ctx.style
    saved = capture_sheet_text(ctx)
    ext = ctx.dwg.Extension
    defaults = 0
    for pid in range(MAX_TEXT_PREF_ID):
        try:
            tf = ext.GetUserPreferenceTextFormat(pid, 0)
        except Exception:
            continue
        if tf is None:
            continue
        try:
            big = float(com.call(tf, "CharHeight")) > st.label_threshold_mm / 1000.0
            tf.TypeFaceName = st.font
            tf.CharHeight = st.label_h if big else st.dim_h
            if ext.SetUserPreferenceTextFormat(pid, 0, tf):
                defaults += 1
        except Exception:
            continue
    prefixes = tuple(p.upper() for p in st.view_label_prefixes)
    count = 0
    for i, v in enumerate(com.views(ctx.dwg)):
        if i == 0:
            continue
        for a in (com.call(v, "GetAnnotations") or []):
            try:
                is_note = int(com.call(a, "GetType")) == ANN_NOTE
                label = False
                if is_note:
                    t = str(com.call(com.call(a, "GetSpecificAnnotation"), "GetText")).upper().strip()
                    label = t.startswith(prefixes)
                try:
                    k_count = max(1, int(com.call(a, "GetTextFormatCount")))
                except Exception:
                    k_count = 1
                for k in range(k_count):
                    tf = a.GetTextFormat(k)
                    if tf is None:
                        continue
                    tf.TypeFaceName = st.font
                    if is_note and not label:
                        tf.CharHeightInPts = st.note_height_pt
                    else:
                        tf.CharHeight = st.label_h if label else st.dim_h
                    a.SetTextFormat(k, False, tf)
                count += 1
            except Exception:
                continue
    restored = restore_sheet_text(saved)
    com.call(ctx.dwg, "GraphicsRedraw2")
    return f"defaults {defaults}, annotations {count}, title-block notes restored {restored}"
