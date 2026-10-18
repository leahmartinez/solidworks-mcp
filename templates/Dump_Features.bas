Attribute VB_Name = "Dump_Features"
' =====================================================================
'  READ-ONLY: writes every feature, sketch and dimension in the ACTIVE
'  part to  %USERPROFILE%\swdraw-output\feature_dump.txt
'  Changes nothing in the model.
'
'  HOW TO RUN
'   1. Make the part you want to inspect the active window
'   2. Tools > Macro > New...  (save anywhere, e.g. Dump.swp)
'   3. In the VBA editor: File > Import File... > pick this .bas
'   4. Put the cursor inside "Sub main" and press F5
' =====================================================================
Option Explicit

Dim fn As Integer

Sub main()
    Dim swApp As Object, m As Object, f As Object, sf As Object
    Set swApp = Application.SldWorks
    Set m = swApp.ActiveDoc
    If m Is Nothing Then
        MsgBox "Open a part and make it the active window first.", vbExclamation
        Exit Sub
    End If

    Dim folder As String, p As String
    folder = Environ("USERPROFILE") & "\swdraw-output\"
    If Dir(folder, vbDirectory) = "" Then MkDir folder
    p = folder & "feature_dump.txt"

    fn = FreeFile
    Open p For Output As #fn
    Print #fn, "FILE" & vbTab & m.GetPathName
    Print #fn, "CONFIG" & vbTab & m.ConfigurationManager.ActiveConfiguration.Name

    Set f = m.FirstFeature
    Do While Not f Is Nothing
        DumpFeat f, 0
        Set sf = f.GetFirstSubFeature
        Do While Not sf Is Nothing
            DumpFeat sf, 1
            Set sf = sf.GetNextSubFeature
        Loop
        Set f = f.GetNextFeature
    Loop

    ' Solid bodies
    Dim bodies As Variant, i As Integer
    bodies = m.GetBodies2(0, False)     ' 0 = solid bodies
    If Not IsEmpty(bodies) Then
        For i = 0 To UBound(bodies)
            Print #fn, "BODY" & vbTab & bodies(i).Name
        Next i
    End If

    Close #fn
    MsgBox "Saved:" & vbCrLf & p, vbInformation
End Sub

Private Sub DumpFeat(f As Object, lvl As Integer)
    Dim s As String, ind As String
    ind = String(lvl * 2, " ")
    s = ind & "FEAT" & vbTab & f.Name & vbTab & f.GetTypeName2
    On Error Resume Next
    Dim sup As Variant
    sup = f.IsSuppressed2(1, Empty)
    If Not IsEmpty(sup) Then s = s & vbTab & "suppressed=" & sup(0)
    On Error GoTo 0
    Print #fn, s

    Dim d As Object, dm As Object
    Set d = f.GetFirstDisplayDimension
    Do While Not d Is Nothing
        Set dm = d.GetDimension2(0)
        If Not dm Is Nothing Then
            Print #fn, ind & "  DIM" & vbTab & dm.FullName & vbTab & _
                       "type=" & d.Type2 & vbTab & _
                       "sys=" & dm.SystemValue & vbTab & _
                       "driven=" & dm.DrivenState
        End If
        Set d = f.GetNextDisplayDimension(d)
    Loop

    ' Sketch relations summary (helps with angle / pattern edits)
    If f.GetTypeName2 = "ProfileFeature" Then
        Dim sk As Object, rm As Object, rels As Variant, j As Integer
        Set sk = f.GetSpecificFeature2
        If Not sk Is Nothing Then
            Set rm = sk.RelationManager
            If Not rm Is Nothing Then
                rels = rm.GetRelations(0)   ' 0 = all
                If Not IsEmpty(rels) Then
                    For j = 0 To UBound(rels)
                        Print #fn, ind & "  REL" & vbTab & rels(j).GetRelationType
                    Next j
                End If
            End If
        End If
    End If
End Sub
