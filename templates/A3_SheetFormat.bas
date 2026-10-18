' =====================================================================
'  A3 sheet format (.slddrt) + drawing template (.drwdot) generator
'   - ISO zoned border (20 mm left, 10 mm elsewhere), cols 1-8, rows A-F
'   - Title block 180 x 56 mm, bottom right
'   - Compact revision block on top of the title block (grows upward)
'   - Optional confidentiality notice, bottom left
'   - General tolerances note, 3rd- or 1st-angle projection symbol
'
'  HOW TO RUN
'   1. SOLIDWORKS > Tools > Macro > New... > save as Build_A3.swp
'   2. In the VBA editor: File > Import File... > pick this .bas
'   3. Edit the constants below, then run "main" (F5).
'      Files are saved to Documents\SOLIDWORKS Templates
'
'  TITLE-BLOCK MODE
'   USE_LINKED_PROPS = True  (recommended): fields are linked to document
'     custom properties ($PRP:"PartNo" ...). Fill them via File > Properties
'     or with swdraw (profiles/title_block.yaml, mode: custom_properties).
'   USE_LINKED_PROPS = False: fields are plain placeholder notes on the sheet
'     layer ("PART-NO", "NAME" ...) that you type over, or that swdraw
'     replaces by position (mode: placeholder_notes).
'
'  All layout coordinates below are in mm, measured from the TOP-LEFT of
'  the sheet, and converted to SOLIDWORKS coordinates (origin bottom-left).
' =====================================================================
Option Explicit

' ------------------------- EDIT THESE ---------------------------------
Const COMPANY          As String = "YOUR COMPANY"
Const OUT_NAME         As String = "A3_Template"
Const FONT_NAME        As String = "Arial"
Const GENERAL_TOL      As String = "GENERAL TOLERANCES TO ISO 2768-mK"
Const THIRD_ANGLE      As Boolean = True    ' False = first-angle
Const USE_LINKED_PROPS As Boolean = True    ' False = placeholder notes
Const SHOW_CONFIDENTIAL As Boolean = True
Const SHEET_W          As Double = 420
Const SHEET_H          As Double = 297
Const W_FRAME          As Double = 0.7      ' line weights, mm
Const W_THICK          As Double = 0.5
' ----------------------------------------------------------------------

Dim swApp   As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2
Dim swDraw  As SldWorks.DrawingDoc
Dim swSk    As SldWorks.SketchManager
Dim gPlaceholders As Collection    ' (text, x, yb, h, bold) added on the sheet layer

Sub main()
    Set swApp = Application.SldWorks
    Set gPlaceholders = New Collection

    Dim tpl As String
    tpl = swApp.GetUserPreferenceStringValue(swDefaultTemplateDrawing)
    If tpl = "" Then
        MsgBox "No default drawing template is set (Tools > Options > Default Templates).", vbExclamation
        Exit Sub
    End If

    Set swModel = swApp.NewDocument(tpl, swDwgPapersUserDefined, SHEET_W / 1000#, SHEET_H / 1000#)
    If swModel Is Nothing Then
        MsgBox "Could not create a new drawing.", vbExclamation
        Exit Sub
    End If
    Set swDraw = swModel

    Dim swSheet As SldWorks.Sheet
    Set swSheet = swDraw.GetCurrentSheet
    swDraw.SetupSheet5 swSheet.GetName, swDwgPapersUserDefined, swDwgTemplateNone, 1, 1, _
                       Not THIRD_ANGLE, "", SHEET_W / 1000#, SHEET_H / 1000#, "Default", True
    swSheet.SheetFormatVisible = True

    swModel.Extension.SetUserPreferenceInteger swDetailingDimensionStandard, 0, swDetailingStandardISO
    swModel.Extension.SetUserPreferenceInteger swUnitSystem, 0, swUnitSystem_MMGS

    ' ---- Build sheet format ----
    swDraw.EditTemplate
    Set swSk = swModel.SketchManager
    swSk.AddToDB = True
    swSk.DisplayWhenAdded = False

    DrawBorderAndZones
    DrawRevisionBlock
    If SHOW_CONFIDENTIAL Then DrawConfidentiality
    DrawTitleBlock

    swSk.AddToDB = False
    swSk.DisplayWhenAdded = True
    swDraw.EditSheet
    swModel.ClearSelection2 True

    If USE_LINKED_PROPS Then
        AddDrawingProps
    Else
        AddPlaceholders       ' editable notes on the sheet layer, not the format
    End If
    swModel.ClearSelection2 True

    swModel.ForceRebuild3 False
    swModel.GraphicsRedraw2

    ' ---- Save ----
    Dim folder As String
    folder = Environ("USERPROFILE") & "\Documents\SOLIDWORKS Templates\"
    If Dir(folder, vbDirectory) = "" Then MkDir folder

    Set swSheet = swDraw.GetCurrentSheet
    swSheet.SaveFormat folder & OUT_NAME & ".slddrt"

    Dim errs As Long, warns As Long
    swModel.Extension.SaveAs folder & OUT_NAME & ".drwdot", swSaveAsCurrentVersion, _
                             swSaveAsOptions_Silent, Nothing, errs, warns

    MsgBox "Saved:" & vbCrLf & folder & OUT_NAME & ".slddrt" & vbCrLf & _
           folder & OUT_NAME & ".drwdot", vbInformation
End Sub

' A title-block value: a linked property, or (placeholder mode) "" here and a
' placeholder note queued for the sheet layer by the caller via VQ.
Private Function V(ByVal prop As String, ByVal placeholder As String) As String
    If USE_LINKED_PROPS Then
        V = "$PRP:""" & prop & """"
    Else
        V = Chr(0) & placeholder        ' marker: Txt queues it instead of drawing it
    End If
End Function

' =====================================================================
'  BORDER + ZONES
' =====================================================================
Private Sub DrawBorderAndZones()
    Dim i As Integer, v As Variant

    Box 20, 10, 410, 287, W_FRAME

    For Each v In Array(68.75, 117.5, 166.25, 215, 263.75, 312.5, 361.25)
        Ln v, 10, v, 5
        Ln v, 287, v, 292
    Next v
    For Each v In Array(56.17, 102.33, 148.5, 194.67, 240.83)
        Ln 20, v, 15, v
        Ln 410, v, 415, v
    Next v

    For i = 0 To 7
        TxtC CStr(i + 1), 44.375 + i * 48.75, 8.4, 2.5
        TxtC CStr(i + 1), 44.375 + i * 48.75, 290.9, 2.5
    Next i
    For i = 0 To 5
        TxtC Chr(65 + i), 17.5, 34 + i * 46.17, 2.5
        TxtC Chr(65 + i), 412.5, 34 + i * 46.17, 2.5
    Next i
End Sub

' =====================================================================
'  REVISION BLOCK  (x 230-410, y 217-231; header at bottom, Rev1 above,
'  Rev2 above that - add rows upward the same way if needed)
' =====================================================================
Private Sub DrawRevisionBlock()
    Box 230, 217, 410, 231, W_THICK
    Ln 230, 222, 410, 222
    Ln 230, 227, 410, 227
    Dim v As Variant
    For Each v In Array(240, 352, 375, 392)
        Ln v, 217, v, 231
    Next v

    TxtC "REV", 235, 229.6, 1.4
    TxtC "REVISION DESCRIPTION", 296, 229.6, 1.4
    TxtC "DATE", 363.5, 229.6, 1.4
    TxtC "DRAWN", 383.5, 229.6, 1.4
    TxtC "APP'D", 401, 229.6, 1.4

    If USE_LINKED_PROPS Then
        RevRowProps "Rev1", 225.3
        RevRowProps "Rev2", 220.3
    End If
End Sub

Private Sub RevRowProps(ByVal p As String, ByVal yb As Double)
    Txt "$PRP:""" & p & """", 233.5, yb, 1.9
    Txt "$PRP:""" & p & "Desc""", 242, yb, 1.9
    Txt "$PRP:""" & p & "Date""", 353.5, yb, 1.9
    Txt "$PRP:""" & p & "By""", 376.5, yb, 1.9
    Txt "$PRP:""" & p & "App""", 393.5, yb, 1.9
End Sub

' =====================================================================
'  CONFIDENTIALITY NOTICE  (bottom left, 80 x 24)
' =====================================================================
Private Sub DrawConfidentiality()
    Box 20, 263, 100, 287, W_THICK
    Txt "CONFIDENTIAL AND PROPRIETARY", 21.5, 267, 1.8, True
    Txt "This drawing and the information it contains are confidential.", 21.5, 270.4, 1.45
    Txt "It is supplied solely for quotation and manufacture of the part", 21.5, 273.1, 1.45
    Txt "shown, and must not be copied, disclosed or used for any other", 21.5, 275.8, 1.45
    Txt "purpose without written permission.", 21.5, 278.5, 1.45
    Txt Chr(169) & " " & Year(Date) & " " & COMPANY, 21.5, 284.6, 1.45
End Sub

' =====================================================================
'  TITLE BLOCK  (x 230-410, y 231-287)
' =====================================================================
Private Sub DrawTitleBlock()
    Box 230, 231, 410, 287, W_THICK
    Ln 230, 247, 410, 247, W_THICK
    Ln 300, 247, 300, 287, W_THICK

    Ln 330, 231, 330, 247
    Ln 380, 231, 380, 247
    Dim v As Variant
    For Each v In Array(255, 263, 271, 279)
        Ln 230, v, 300, v
    Next v
    Ln 278, 247, 278, 263
    Ln 258, 279, 258, 287
    Ln 300, 261, 410, 261
    Ln 300, 275, 410, 275
    For Each v In Array(355, 370, 390)
        Ln v, 275, v, 287
    Next v

    ' --- Notes strip ---
    Txt "UNLESS OTHERWISE SPECIFIED:", 231.5, 234.2, 1.6, True
    Txt "DIMENSIONS IN MILLIMETRES", 231.5, 237.1, 1.6
    Txt GENERAL_TOL, 231.5, 240, 1.6
    Txt "REMOVE ALL BURRS AND SHARP EDGES", 231.5, 242.9, 1.6
    Txt "DO NOT SCALE DRAWING", 231.5, 245.8, 1.6, True

    ' --- Status ---
    Txt "STATUS", 331.2, 233.3, 1.5
    Txt V("Status", "DRAFT"), 332, 242.4, 3.4, True

    ' --- Projection symbol ---
    If THIRD_ANGLE Then
        TxtC "3RD ANGLE", 395, 233.3, 1.5
        Circ 388, 240, 4
        Circ 388, 240, 2
        Cone 394, 405
    Else
        TxtC "1ST ANGLE", 395, 233.3, 1.5
        Cone 383, 394
        Circ 401, 240, 4
        Circ 401, 240, 2
    End If

    ' --- Left column ---
    Lbl "DRAWN", 231.2, 249.3:    Txt V("DrawnBy", "NAME"), 231.2, 253.5, 2.6
    Lbl "DATE", 279.2, 249.3:     Txt V("DrawnDate", "DD/MM/YYYY"), 279.2, 253.5, 2.2
    Lbl "APPROVED", 231.2, 257.3: Txt V("ApprovedBy", "NAME"), 231.2, 261.5, 2.6
    Lbl "DATE", 279.2, 257.3:     Txt V("ApprovedDate", "DD/MM/YYYY"), 279.2, 261.5, 2.2
    Lbl "MATERIAL", 231.2, 265.3: Txt V("Material", "MATERIAL SPECIFICATION"), 231.2, 269.5, 2.6
    Lbl "FINISH / TREATMENT", 231.2, 273.3
    Txt V("Finish", "FINISH / TREATMENT"), 231.2, 277.5, 2.3
    Lbl "PROJECT", 231.2, 281.3:  Txt V("Project", "PROJECT"), 231.2, 285.5, 2.6
    Lbl "PARENT ASSEMBLY", 259.2, 281.3
    Txt V("ParentAssy", "ASSEMBLY NO."), 259.2, 285.5, 2.6

    ' --- Right column ---
    Txt COMPANY, 302.5, 256.6, 6, True, 1.4
    Lbl "TITLE", 301.2, 263.3:        Txt V("Description", "PART DESCRIPTION"), 301.2, 270.6, 3.5
    Lbl "DRAWING NO.", 301.2, 277.3:  Txt V("PartNo", "PART-NO"), 301.2, 284.6, 3.5, True
    Lbl "REV", 356.2, 277.3:          Txt V("Revision", "A"), 358.5, 284.6, 3.5, True
    Lbl "SCALE", 371.2, 277.3:        Txt "$PRP:""SW-Sheet Scale""", 372, 284.6, 3
    Lbl "SHEET", 391.2, 277.3
    Txt "$PRP:""SW-Current Sheet"" OF $PRP:""SW-Total Sheets""", 391.5, 284.6, 2.4
End Sub

' =====================================================================
'  DRAWING PROPERTIES (linked mode; filled per drawing via File > Properties)
' =====================================================================
Private Sub AddDrawingProps()
    Dim cpm As SldWorks.CustomPropertyManager
    Set cpm = swModel.Extension.CustomPropertyManager("")

    SetProp cpm, "Status", "DRAFT"
    SetProp cpm, "Revision", "A"
    Dim p As Variant
    For Each p In Array("DrawnBy", "DrawnDate", "ApprovedBy", "ApprovedDate", _
                        "Rev1", "Rev1Desc", "Rev1Date", "Rev1By", "Rev1App", _
                        "Rev2", "Rev2Desc", "Rev2Date", "Rev2By", "Rev2App")
        SetProp cpm, CStr(p), " "
    Next p
End Sub

Private Sub SetProp(cpm As SldWorks.CustomPropertyManager, ByVal nm As String, ByVal val As String)
    cpm.Add3 nm, swCustomInfoText, val, swCustomPropertyReplaceValue
End Sub

' =====================================================================
'  PLACEHOLDERS (placeholder mode) - plain notes on the SHEET layer, so in
'  a new drawing you double-click any of them and type over it.
' =====================================================================
Private Sub AddPlaceholders()
    ' Revision block (Rev A row sits on the header; Rev B above it)
    PlaceRevRow "A", "FIRST ISSUE", 225.3
    PlaceRevRow "B", "REVISION DESCRIPTION", 220.3

    Dim item As Variant
    For Each item In gPlaceholders
        MakeNote item(0), item(1), item(2), item(3), item(4), 0
    Next item
End Sub

Private Sub PlaceRevRow(ByVal rv As String, ByVal desc As String, ByVal yb As Double)
    MakeNote rv, 233.5, yb, 1.9, False, 0
    MakeNote desc, 242, yb, 1.9, False, 0
    MakeNote "DD/MM/YYYY", 353.5, yb, 1.9, False, 0
    MakeNote "XX", 376.5, yb, 1.9, False, 0
    MakeNote "XX", 393.5, yb, 1.9, False, 0
End Sub

' =====================================================================
'  HELPERS  (inputs in mm, top-left origin; converted here)
' =====================================================================
Private Function SY(ByVal y As Double) As Double
    SY = (SHEET_H - y) / 1000#
End Function

Private Sub Ln(ByVal x1 As Double, ByVal y1 As Double, ByVal x2 As Double, ByVal y2 As Double, _
               Optional ByVal wmm As Double = 0)
    Dim seg As SldWorks.SketchSegment
    Set seg = swSk.CreateLine(x1 / 1000#, SY(y1), 0, x2 / 1000#, SY(y2), 0)
    If wmm > 0 And Not seg Is Nothing Then
        swModel.ClearSelection2 True
        seg.Select4 False, Nothing
        swModel.SetLineWidthCustom wmm / 1000#
        swModel.ClearSelection2 True
    End If
End Sub

Private Sub Box(ByVal x1 As Double, ByVal y1 As Double, ByVal x2 As Double, ByVal y2 As Double, _
                Optional ByVal wmm As Double = 0)
    Ln x1, y1, x2, y1, wmm: Ln x2, y1, x2, y2, wmm
    Ln x2, y2, x1, y2, wmm: Ln x1, y2, x1, y1, wmm
End Sub

Private Sub Circ(ByVal xc As Double, ByVal yc As Double, ByVal r As Double)
    swSk.CreateCircleByRadius xc / 1000#, SY(yc), 0, r / 1000#
End Sub

' Truncated cone side view, small end on the left
Private Sub Cone(ByVal xa As Double, ByVal xb As Double)
    Ln xa, 238, xb, 236
    Ln xb, 236, xb, 244
    Ln xb, 244, xa, 242
    Ln xa, 242, xa, 238
End Sub

Private Sub Lbl(ByVal s As String, ByVal x As Double, ByVal yb As Double)
    Txt s, x, yb, 1.5
End Sub

' Left-aligned note; (x, yb) = left end of the text baseline
Private Sub Txt(ByVal s As String, ByVal x As Double, ByVal yb As Double, ByVal h As Double, _
                Optional ByVal isBold As Boolean = False, Optional ByVal spacing As Double = 0)
    If Left(s, 1) = Chr(0) Then           ' placeholder: add later on the sheet layer
        gPlaceholders.Add Array(Mid(s, 2), x, yb, h, isBold)
        Exit Sub
    End If
    Dim n As SldWorks.Note
    Set n = MakeNote(s, x, yb, h, isBold, spacing)
End Sub

' Centred note; (xc, yb) = centre of the text baseline
Private Sub TxtC(ByVal s As String, ByVal xc As Double, ByVal yb As Double, ByVal h As Double, _
                 Optional ByVal isBold As Boolean = False)
    Dim n As SldWorks.Note
    Set n = MakeNote(s, xc, yb, h, isBold, 0)
    If n Is Nothing Then Exit Sub

    Dim w As Double, e As Variant
    w = Len(s) * h * 0.62                     ' fallback estimate
    On Error Resume Next
    e = n.GetExtent
    If Not IsEmpty(e) Then
        If e(3) > e(0) Then w = (e(3) - e(0)) * 1000#
    End If
    On Error GoTo 0
    n.GetAnnotation.SetPosition2 (xc - w / 2) / 1000#, SY(yb) + h * 0.9 / 1000#, 0
End Sub

Private Function MakeNote(ByVal s As String, ByVal x As Double, ByVal yb As Double, ByVal h As Double, _
                          ByVal isBold As Boolean, ByVal spacing As Double) As SldWorks.Note
    Dim n As SldWorks.Note, a As SldWorks.Annotation, tf As SldWorks.TextFormat

    swModel.ClearSelection2 True              ' no selection = no leader
    Set n = swModel.InsertNote(s)
    If n Is Nothing Then Exit Function
    Set a = n.GetAnnotation

    Set tf = a.GetTextFormat(0)
    tf.TypeFaceName = FONT_NAME
    tf.CharHeight = h / 1000#
    tf.Bold = isBold
    If spacing > 0 Then
        On Error Resume Next
        tf.CharSpacingFactor = spacing
        On Error GoTo 0
    End If
    a.SetTextFormat 0, False, tf

    ' SOLIDWORKS positions notes by their top-left corner
    a.SetPosition2 x / 1000#, SY(yb) + h * 0.9 / 1000#, 0
    Set MakeNote = n
End Function
