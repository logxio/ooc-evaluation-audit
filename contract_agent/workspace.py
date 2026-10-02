"""Structured source workspaces, preserving cell styles and PDF word geometry."""
import argparse
from collections import defaultdict
import copy
import colorsys
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def text(node):return ' '.join(''.join(node.itertext()).split())


def fill_style(fill,theme):
    color=fill.fgColor
    item={'fill_type':fill.patternType,'color_type':color.type,'color':str(color.value),'tint':float(color.tint)}
    rgb=None
    if color.type=='rgb':rgb=color.rgb[-6:]
    elif color.type=='indexed':
        from openpyxl.styles.colors import COLOR_INDEXED
        if color.indexed<len(COLOR_INDEXED):rgb=COLOR_INDEXED[color.indexed][-6:]
    elif color.type=='theme' and color.theme<len(theme):rgb=theme[color.theme]
    if rgb:
        channels=[int(rgb[i:i+2],16)/255 for i in (0,2,4)]
        h,l,s=colorsys.rgb_to_hls(*channels);tint=float(color.tint)
        l=l*(1+tint) if tint<0 else l*(1-tint)+tint
        item['resolved_rgb']=''.join(f'{round(c*255):02X}' for c in colorsys.hls_to_rgb(h,l,s))
    return item


def parse_file(path):
    tables={};cells={};styles={}
    if path.suffix=='.xlsx':
        import openpyxl
        workbook=openpyxl.load_workbook(path,data_only=True)
        theme=[]
        if workbook.loaded_theme:
            namespace={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
            scheme=ET.fromstring(workbook.loaded_theme).find('.//a:clrScheme',namespace)
            if scheme is not None:
                by_name={node.tag.rsplit('}',1)[-1]:next(iter(node)).attrib for node in scheme}
                for name in ['lt1','dk1','lt2','dk2','accent1','accent2','accent3','accent4','accent5','accent6','hlink','folHlink']:
                    value=by_name.get(name,{})
                    theme.append(value.get('lastClr',value.get('val','FFFFFF')))
        for sheet in workbook:
            rows=[]
            if sheet.max_row*sheet.max_column>2_000_000:
                tables[sheet.title]={'error':'Sheet exceeds 2 million cell parsing limit','nrows':sheet.max_row,'ncols':sheet.max_column};continue
            for row in sheet:
                values=[]
                for cell in row:
                    value=cell.value
                    if hasattr(value,'isoformat'):value=value.isoformat()
                    values.append(value)
                    key=f'{path.name}/{sheet.title}/{cell.coordinate}'
                    if value is not None:cells[key]=value
                    fill=cell.fill
                    if fill.patternType:
                        styles[key]=fill_style(fill,theme)
                rows.append(values)
            tables[sheet.title]={'rows':rows,'nrows':sheet.max_row,'ncols':sheet.max_column,
                                'merged':[str(x) for x in sheet.merged_cells.ranges]}
    elif path.suffix=='.xls':
        import xlrd
        workbook=xlrd.open_workbook(path,formatting_info=True)
        for sheet in workbook.sheets():
            rows=[sheet.row_values(i) for i in range(sheet.nrows)]
            tables[sheet.name]={'rows':rows,'nrows':sheet.nrows,'ncols':sheet.ncols}
            for r,row in enumerate(rows,1):
                for c,value in enumerate(row,1):
                    if value!='':cells[f'{path.name}/{sheet.name}/R{r}C{c}']=value
    elif path.suffix in ('.csv','.tsv'):
        rows=list(csv.reader(path.open(errors='replace'),delimiter='\t' if path.suffix=='.tsv' else ','))
        tables['data']={'rows':rows,'nrows':len(rows),'ncols':max(map(len,rows),default=0)}
        for r,row in enumerate(rows,1):
            for c,value in enumerate(row,1):cells[f'{path.name}/data/R{r}C{c}']=value
    elif path.suffix=='.docx':
        # Word supplements: every body table keeps its rows (a merged span repeats as empty cells, so columns
        # stay under their headers) and the paragraph just above it as caption; paragraphs join the article search.
        W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        def flat(node):return ' '.join(''.join(t.text or '' for t in node.iter(W+'t')).split())
        with ZipFile(path) as archive:body=ET.fromstring(archive.read('word/document.xml')).find(W+'body')
        caption='';paragraphs=[]
        for child in body:
            if child.tag==W+'p':
                value=flat(child)
                if value:caption=value;paragraphs.append(value)
            elif child.tag==W+'tbl':
                rows=[]
                for tr in child.findall(W+'tr'):
                    row=[]
                    for tc in tr.findall(W+'tc'):
                        span=tc.find(W+'tcPr/'+W+'gridSpan')
                        row+=[flat(tc)]+['']*(int(span.get(W+'val','1'))-1 if span is not None else 0)
                    rows.append(row)
                name=f'table{len(tables)+1}'
                tables[name]={'rows':rows,'nrows':len(rows),'ncols':max(map(len,rows),default=0),'caption':caption[:600]}
                for r,row in enumerate(rows,1):
                    for c,value in enumerate(row,1):
                        if value!='':cells[f'{path.name}/{name}/R{r}C{c}']=value
        return {'tables':tables,'cells':cells,'styles':styles,'paragraphs':paragraphs}
    elif path.suffix=='.pdf':
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for n,page in enumerate(pdf.pages,1):
                words=page.extract_words(x_tolerance=2,y_tolerance=3)
                groups=[]
                for word in sorted(words,key=lambda w:(round(w['top']/3),w['x0'])):
                    if not groups or abs(groups[-1]['y']-word['top'])>3:
                        groups.append({'y':round(word['top'],2),'cells':[]})
                    groups[-1]['cells'].append({'text':word['text'],'x0':round(word['x0'],2),'x1':round(word['x1'],2)})
                for row in groups:row['cells'].sort(key=lambda w:w['x0'])
                rows=[[w['text'] for w in row['cells']] for row in groups]
                for r,row in enumerate(rows,1):
                    for c,value in enumerate(row,1):cells[f'{path.name}/page{n}/R{r}C{c}']=value
                tables[f'page{n}']={'rows':rows,'geometry':groups,'nrows':len(rows),
                                    'ncols':max(map(len,rows),default=0),'width':float(page.width),'height':float(page.height)}
    elif path.suffix=='.xml':
        root=ET.parse(path).getroot()
        for n,table in enumerate(root.iter('table-wrap'),1):
            label=table.find('label');name=text(label) if label is not None else f'Table {n}'
            rows=[[text(c) for c in row if c.tag in ['td','th']] for row in table.iter('tr')]
            tables[name]={'rows':rows,'nrows':len(rows),'ncols':max(map(len,rows),default=0)}
            for r,row in enumerate(rows,1):
                for c,value in enumerate(row,1):cells[f'{path.name}/{name}/R{r}C{c}']=value
    return {'tables':tables,'cells':cells,'styles':styles}


def prepare(original,output):
    output.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((original/'receipt.json').read_text())
    for entry in receipt['sources']:
        path=original/entry['file']
        if path.exists():shutil.copyfile(path,output/path.name)
    root=ET.parse(original/'article.xml').getroot()
    href='{http://www.w3.org/1999/xlink}href'
    inventory={entry['file']:{**entry,'status':'local'} for entry in receipt['sources']}
    for element in root.iter():
        if element.tag not in ['graphic','media']:continue
        name=element.attrib.get(href,'')
        if not name or '/' in name or name in inventory:continue
        caption=''
        for parent in root.iter():
            if element in list(parent):caption=text(parent)[:1200];break
        inventory[name]={'file':name,'url':f'https://pmc-oa-opendata.s3.amazonaws.com/{receipt["pmcid"]}.1/{name}',
                         'caption':caption,'status':'listed'}
    for item in inventory.values():
        path=output/item['file']
        if path.suffix.lower() not in ['.xml','.pdf','.xlsx','.xls','.csv','.tsv','.docx','.doc','.jpg','.jpeg','.png','.tif','.tiff','.webp','.zip']:continue
        if not path.exists():
            try:
                request=urllib.request.Request(item['url'],headers={'User-Agent':'Executable-contract-research/2.0'})
                with urllib.request.urlopen(request,timeout=45) as response:path.write_bytes(response.read(120_000_001))
                if path.stat().st_size>120_000_000:raise ValueError('Source file exceeds 120 MB limit')
            except Exception as exc:
                item['status']='error';item['error']=f'{type(exc).__name__}: {exc}';continue
        item.update(status='local',sha256=sha(path),bytes=path.stat().st_size)
    for path in list(output.glob('*.zip')):
        with ZipFile(path) as archive:
            for member in archive.infolist():
                if Path(member.filename).suffix.lower() not in ['.xlsx','.xls','.csv','.tsv','.pdf','.docx']:continue
                if member.file_size>60_000_000 or Path(member.filename).name.startswith('._'):continue
                name=Path(member.filename).name
                target=output/name
                target.write_bytes(archive.read(member))
                inventory[name]={'file':name,'archive':path.name,'member':member.filename,'status':'local',
                                 'sha256':sha(target),'bytes':target.stat().st_size}
    for path in list(output.glob('*.doc')):
        # Legacy Word binaries become .docx with the macOS converter; the original stays listed beside it.
        target=path.with_suffix('.docx')
        if not target.exists():subprocess.run(['/usr/bin/textutil','-convert','docx','-output',str(target),str(path)],check=True,capture_output=True)
        inventory[target.name]={'file':target.name,'converted_from':path.name,'status':'local','sha256':sha(target),'bytes':target.stat().st_size}
    for path in list(output.glob('*.docx')):
        # Figures embedded in a Word supplement become viewable images of their own.
        with ZipFile(path) as archive:
            for member in archive.infolist():
                if not member.filename.startswith('word/media/') or Path(member.filename).suffix.lower() not in ['.png','.jpg','.jpeg','.tif','.tiff']:continue
                name=f'{path.stem}_{Path(member.filename).name}';target=output/name
                target.write_bytes(archive.read(member))
                inventory[name]={'file':name,'archive':path.name,'member':member.filename,'status':'local','sha256':sha(target),'bytes':target.stat().st_size}
    # Preserve the original normalized lookup too; labels below use the new files.
    article=copy.deepcopy(root)
    for parent in article.iter():
        for child in list(parent):
            if child.tag in ['table-wrap','ref-list']:parent.remove(child)
    paragraphs=[{'ref':f'article:p{n}','text':text(p)} for n,p in enumerate(article.iter('p'),1)]
    parsed={};cells={};styles={}
    for name,item in list(inventory.items()):
        path=output/name
        if item['status']!='local' or path.suffix.lower() not in ['.xml','.pdf','.xlsx','.xls','.csv','.tsv','.docx']:continue
        try:
            data=parse_file(path);parsed[name]=data['tables'];cells.update(data['cells']);styles.update(data['styles'])
            paragraphs+=[{'ref':f'{name}:p{n}','text':value} for n,value in enumerate(data.get('paragraphs',[]),1)]
            item['sheets']=[{'name':k,'nrows':v.get('nrows'),'ncols':v.get('ncols'),**({'caption':v['caption']} if v.get('caption') else {}),
                             **({'error':v['error']} if 'error' in v else {})} for k,v in data['tables'].items()]
        except Exception as exc:item['parse_error']=f'{type(exc).__name__}: {exc}'
    (output/'article.json').write_text(json.dumps(paragraphs,ensure_ascii=False,indent=2))
    for p in paragraphs:cells[p['ref']]=p['text']
    for name,obj in [('tables.json',parsed),('cells.json',cells),('styles.json',styles),('inventory.json',list(inventory.values())),('provenance.json',receipt)]:
        (output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps({'paper':output.name,'files':len(inventory),'local':sum(x['status']=='local' for x in inventory.values()),
                      'tables':sum(len(v) for v in parsed.values()),'cells':len(cells),'styled_cells':len(styles),
                      'errors':[x for x in inventory.values() if x['status']=='error' or 'parse_error' in x]}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();prepare(a.original,a.output)


if __name__=='__main__':main()
