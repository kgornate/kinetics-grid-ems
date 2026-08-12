import 'dart:convert';
import 'dart:typed_data';

import 'package:archive/archive.dart';

class FastBessHistoryExporter {
  const FastBessHistoryExporter._();

  static Uint8List buildCsvBytes({
    required List<String> headers,
    required List<List<Object?>> rows,
  }) {
    final buffer = StringBuffer();
    // UTF-8 BOM helps Microsoft Excel open the CSV with correct encoding.
    buffer.write('\ufeff');
    buffer.writeln(headers.map(_csvEscape).join(','));
    for (final row in rows) {
      buffer.writeln(row.map(_csvEscape).join(','));
    }
    return Uint8List.fromList(utf8.encode(buffer.toString()));
  }

  static Uint8List buildXlsxBytes({
    required String sheetName,
    required List<String> headers,
    required List<List<Object?>> rows,
  }) {
    final archive = Archive();
    _addTextFile(archive, '[Content_Types].xml', _contentTypesXml);
    _addTextFile(archive, '_rels/.rels', _rootRelsXml);
    _addTextFile(archive, 'xl/workbook.xml', _workbookXml(_sanitizeSheetName(sheetName)));
    _addTextFile(archive, 'xl/_rels/workbook.xml.rels', _workbookRelsXml);
    _addTextFile(archive, 'xl/styles.xml', _stylesXml);
    _addTextFile(archive, 'xl/worksheets/sheet1.xml', _worksheetXml(headers, rows));

    final encoded = ZipEncoder().encode(archive);
    if (encoded == null) {
      throw StateError('Failed to encode XLSX archive.');
    }
    return Uint8List.fromList(encoded);
  }

  static void _addTextFile(Archive archive, String name, String content) {
    final bytes = utf8.encode(content);
    archive.addFile(ArchiveFile(name, bytes.length, bytes));
  }

  static String _worksheetXml(List<String> headers, List<List<Object?>> rows) {
    final xmlRows = StringBuffer();
    xmlRows.write('<row r="1">');
    for (var col = 0; col < headers.length; col++) {
      xmlRows.write(_cell(1, col + 1, headers[col], style: 1));
    }
    xmlRows.write('</row>');

    for (var index = 0; index < rows.length; index++) {
      final rowNumber = index + 2;
      final row = rows[index];
      xmlRows.write('<row r="$rowNumber">');
      for (var col = 0; col < headers.length; col++) {
        final value = col < row.length ? row[col] : null;
        xmlRows.write(_cell(rowNumber, col + 1, value));
      }
      xmlRows.write('</row>');
    }

    final columnCount = headers.length;
    final dimension = columnCount <= 0
        ? 'A1:A1'
        : 'A1:${_columnName(columnCount)}${rows.length + 1}';

    final columnWidths = StringBuffer();
    for (var col = 1; col <= columnCount; col++) {
      final width = col <= 5 ? 22 : 18;
      columnWidths.write('<col min="$col" max="$col" width="$width" customWidth="1"/>');
    }

    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <dimension ref="$dimension"/>
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
    </sheetView>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>$columnWidths</cols>
  <sheetData>$xmlRows</sheetData>
  <autoFilter ref="$dimension"/>
</worksheet>''';
  }

  static String _cell(int row, int col, Object? value, {int? style}) {
    final ref = '${_columnName(col)}$row';
    final styleAttr = style == null ? '' : ' s="$style"';
    if (value is num && value.isFinite) {
      return '<c r="$ref"$styleAttr><v>${value.toString()}</v></c>';
    }
    final text = _xmlEscape(value?.toString() ?? '');
    return '<c r="$ref" t="inlineStr"$styleAttr><is><t>$text</t></is></c>';
  }

  static String _columnName(int columnNumber) {
    var number = columnNumber;
    final chars = <int>[];
    while (number > 0) {
      number--;
      chars.insert(0, 65 + (number % 26));
      number ~/= 26;
    }
    return String.fromCharCodes(chars);
  }

  static String _csvEscape(Object? value) {
    final text = value?.toString() ?? '';
    final escaped = text.replaceAll('"', '""');
    if (escaped.contains(',') || escaped.contains('\n') || escaped.contains('\r') || escaped.contains('"')) {
      return '"$escaped"';
    }
    return escaped;
  }

  static String _xmlEscape(String value) {
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&apos;');
  }

  static String _sanitizeSheetName(String value) {
    final cleaned = value.replaceAll(RegExp(r'[\\/*?:\[\]]'), ' ').trim();
    if (cleaned.isEmpty) return 'Fast BESS History';
    return cleaned.length > 31 ? cleaned.substring(0, 31) : cleaned;
  }

  static const String _contentTypesXml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>''';

  static const String _rootRelsXml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''';

  static String _workbookXml(String sheetName) => '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="${_xmlEscape(sheetName)}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>''';

  static const String _workbookRelsXml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''';

  static const String _stylesXml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>''';
}
