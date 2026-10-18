# SolidWorks API gotchas

Read this when a SolidWorks call misbehaves or before changing code that talks to SolidWorks.

Lessons from building drawings through the SolidWorks API from Python. swdraw already handles
everything here; this file explains why the code looks the way it does.

## Python and COM

- **Use late binding** (`win32com.client.dynamic.Dispatch`). Early-bound wrappers from `makepy`
  disagree with some SolidWorks signatures. Under late binding pywin32 can't always tell a
  zero-argument method from a property, so `swdraw.com.call(obj, "Name", *args)` accepts either.
- **Null object arguments**: pass `VARIANT(pythoncom.VT_DISPATCH, None)` where the API expects
  `Nothing` (for example the callout argument of `SelectByID2`, or `Select3`). Plain `None` gives
  *Type mismatch*. Use `swdraw.com.nothing()`.
- **By-reference arguments**: the errors and warnings arguments of `OpenDoc6` (and `SaveAs`) need
  `VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)`. Use `swdraw.com.byref_int()`.
- **Some insert calls only work through an explicit `IDispatch::Invoke`**: `InsertGtol` and
  `InsertDatumTag2` (also `SetLabel` on the datum tag). Use `swdraw.com.invoke(obj, "InsertGtol")`.
- **Arrays** (view positions, scale ratios) must be `VARIANT(VT_ARRAY | VT_R8, [...])`. Use
  `swdraw.com.arr8()`.

## Selecting and deleting

- **The view is often auto-selected as item 1.** `SelectByID2` can return True while it has
  selected the view rather than an edge. Judge a pick by the selection count growing *and* the last
  item's type being an edge (1), vertex (3) or silhouette (46). Nudging the pick ±0.2 mm and trying
  the other entity kinds rescues most misses.
- **Deleting a note**: `Annotation.Select2(False, 0)` then `EditDelete` works where `Select3`
  returns False. Fall back to `SelectByID2("<name>@<view>", "NOTE", ...)`.
- **Dimensions** are easiest to delete by name: `GetNameForSelection`, then `SelectByID2(name,
  "DIMENSION", ...)`.
- **Dangling centre marks** (left behind by deleted features) often can't be selected or deleted
  through the API at all. swdraw tries several selection types; whatever survives needs a manual
  delete. `swdraw diag annotations` lists them.
- **Sheet-format notes can't be deleted from the sheet.** When clearing, swdraw blanks them (sets
  the text to a single space) instead.

## Geometry and coordinates

- **Model to sheet**: use `View.ModelToViewTransform.ArrayData` (16 values):
  - `sheet_x = sc * (X*a0 + Y*a3 + Z*a6) + a9`
  - `sheet_y = sc * (X*a1 + Y*a4 + Z*a7) + a10`
  - `sc = a12`

  Model coordinates in metres, sheet in metres. `swdraw.geometry.model_to_sheet` takes model mm.
- **View sketch space**: sketch entities inside a view (section lines, detail circles) are in
  `(sheet - view position) / view scale`, from `View.GetXform`, not in sheet coordinates. A
  section line drawn in sheet coordinates lands somewhere else entirely.
- **Regenerate before picking edges**: `ForceRebuild3(False)`, `ViewZoomtofit2`, `GraphicsRedraw2`,
  then a short pause. Otherwise newly created section and detail views can have blank geometry
  and picks land on the wrong edges, or on nothing.
- **Sections cut from the top view can come out upside down**, and rotating the view afterwards
  breaks its transform (picks no longer line up). Cut from the opposite view instead, check
  `ArrayData[4] > 0` (model +Y up), and if needed `RemoveAlignment` and reposition. In a spec:
  `from_views: [bottom, top]` with `require_upright: true`.
- **Scale before position**: changing a view's scale moves it, so set every scale, rebuild, then
  set positions.

## Dimensions and GD&T

- **Tolerances**: set `Tolerance.Type`, then `Tolerance.SetValues2(lo, hi, ...)` (or `SetValues`)
  in **metres**, then read back `GetMinValue` and `GetMaxValue`. A call that silently fails shows
  as ±0.00 on the sheet.
- **Check every dimension's value.** A pick can succeed on the wrong edge, so compare
  `Dimension.SystemValue` with what you expect and retry if it's off. This is the main idea in
  swdraw.
- **Arc end conditions** (min/centre/max distance to an arc) are set with
  `IDimension.SetArcEndCondition`, not on the display dimension. Try the conditions until the value
  matches.
- **GD&T frames**: `SetFrameSymbols2(i, "<GTOL-SRUN>", ...)` and `SetFrameValues(i, tol, "", d1, d2,
  "")` per frame row. `SetText(3, text)` puts text such as "ALL AROUND" above the frame.
- **Datum tags** attached to a dimension keep SolidWorks' own placement. Attached to an edge, you
  have to position them.

## Notes and fonts

- **`Note.SetText` drops SolidWorks' automatic list numbering.** To change a numbered notes block,
  delete it and re-insert it with literal "1.  ", "2.  " prefixes (`swdraw notes replace`). If you
  find an un-numbered duplicate, `swdraw notes dedupe` removes it.
- **Changing document text defaults resizes title-block notes too.** Capture their font, height
  and bold first, then restore them (the `fonts` step does this).
- **Notes are positioned by their top-left corner**, which is also what `GetPosition` returns.
- **Empty note text deletes the note**, so blank a field with a single space.

## Files and references

- **Reference-safe rename**: Save As the part *while its drawing is open*. The open drawing
  re-points to the new file. Then Save As the drawing. Renaming in Explorer breaks the reference.
- **File locks**: SolidWorks keeps renamed or replaced files locked until the documents are closed.
  Close them (`CloseDoc`), wait a moment, then move the old files.
- **Derived parts** (for example, bodies inserted from a multi-body master part) need the master to
  stay in a folder SolidWorks searches. Moving it into a subfolder such as `_Superseded` breaks the
  link. Keep masters in the working folder (add them to `keep` in `tidy`).
- **After moving or renaming folders**, reopen each drawing from its new location, rebuild and save
  so the stored reference paths update. `renumber` with `supersede` does this and reports any
  dependency that no longer exists.
- **Check save results.** `SaveAs3` returns an error code and `Save2` returns a bool. A save can
  be refused (read-only file, file open elsewhere) without raising.
