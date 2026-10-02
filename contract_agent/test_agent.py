"""Offline integration tests, not model-accuracy observations."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

from .agent_tools import TOOLS,Workbench
from .agent import cost,token_upper
from .engine import extract_value
from .workspace import fill_style


class AgentChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        source=self.root/'source';source.mkdir();self.source=source
        for name,data in [('cells',{'table.csv/data/R1C1':4}),('tables',{'table.csv':{'data':{'rows':[[4]],'nrows':1,'ncols':1}}}),
                          ('styles',{}),('article',[]),('inventory',[])]:
            (source/f'{name}.json').write_text(json.dumps(data))
        self.workbench=Workbench(source,self.root/'scratch','fixture')

    def tearDown(self):self.temp.cleanup()

    def test_structured_preview_preserves_reference(self):
        data,_=self.workbench.call('preview_table',{'file':'table.csv','sheet':'data'})
        self.assertEqual(data['rows'][0]['cells'][0],{'ref':'table.csv/data/R1C1','value':4})

    def test_figure_values_come_only_from_the_blind_reader(self):
        from PIL import Image
        Image.new('RGB',(40,20),'white').save(self.source/'figure.png')
        with self.assertRaisesRegex(RuntimeError,'independent figure reader'):
            self.workbench.call('read_figure',{'file':'figure.png'})
        seen=[]
        def reader(png):
            seen.append(png);return {'rows':[['P1','Sensitive'],['P2','']],'uncertain':[[1,2]]}
        workbench=Workbench(self.source,self.root/'scratch','fixture',reader)
        data,_=workbench.call('read_figure',{'file':'figure.png','crop':[0,0,.5,1]})
        stem='vision/'+data['image_sha256'][:12]
        self.assertEqual(data['rows'][0]['cells'][1],{'ref':f'{stem}/R1C2','value':'Sensitive','uncertain':True})
        self.assertEqual(workbench.index()[f'{stem}/R2C1'],'P2');self.assertNotIn(f'{stem}/R2C2',workbench.index())
        self.assertEqual(len(seen),1);self.assertIn('crop',data['source'])
        self.assertTrue(any('Uncertain visual label' in e for e in workbench.check(
            {'fields':{},'headline':{'metric':'accuracy','records':[{'id':'a','score':{'ref':f'{stem}/R1C2','map':{'Sensitive':1}},'truth':{'ref':'table.csv/data/R1C1'}}]}},
            {'metric':'accuracy','value':1,'n':1,'tolerance':0})['errors']))
        self.assertNotIn('record_visual_labels',[t['function']['name'] for t in TOOLS])

    def test_refusal_is_separate_from_numerical_pass(self):
        result=self.workbench.check({'status':'no_headline','headline':{'records':[]}},None)
        self.assertTrue(result['correct_refusal']);self.assertFalse(result['matched'])

    def test_source_arithmetic(self):
        self.assertEqual(extract_value({'calc':'divide','args':[{'ref':'x'},2]},{'x':8}),4)

    def test_pure_literal_calculation_rejected(self):
        with self.assertRaisesRegex(ValueError,'source reference'):
            extract_value({'calc':'divide','args':[8,2]}, {})

    def test_word_supplement_tables_keep_columns_and_caption(self):
        from zipfile import ZipFile
        from .workspace import parse_file
        w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        def cell(text,span=None):return f'<w:tc>{f"<w:tcPr><w:gridSpan w:val=\"{span}\"/></w:tcPr>" if span else ""}<w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>'
        body=(f'<w:p><w:r><w:t>Table S2. Organoid response per patient</w:t></w:r></w:p><w:tbl><w:tr>{cell("Patient")}{cell("Response",2)}</w:tr>'
              f'<w:tr>{cell("P1")}{cell("PR")}{cell("0.42")}</w:tr></w:tbl>')
        path=self.root/'supp.docx'
        with ZipFile(path,'w') as z:z.writestr('word/document.xml',f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
        data=parse_file(path)
        self.assertEqual(data['tables']['table1']['rows'],[['Patient','Response',''],['P1','PR','0.42']])
        self.assertEqual(data['tables']['table1']['caption'],'Table S2. Organoid response per patient')
        self.assertEqual(data['cells']['supp.docx/table1/R2C3'],'0.42');self.assertEqual(data['paragraphs'],['Table S2. Organoid response per patient'])

    def test_workbook_theme_and_tint_are_resolved(self):
        color=SimpleNamespace(type='theme',value=0,theme=0,tint=.5)
        style=fill_style(SimpleNamespace(fgColor=color,patternType='solid'),['000000'])
        self.assertEqual(style['resolved_rgb'],'808080')

    def test_grid_colours_are_read_without_a_model(self):
        from PIL import Image,ImageDraw
        from .grid_colors import grid
        image=Image.new('RGB',(200,120),'white');draw=ImageDraw.Draw(image)
        palette=[[(232,64,56),(196,188,132),(40,60,150)],[(150,200,110),(240,190,50),(232,64,56)]]
        for r,row in enumerate(palette):
            for c,rgb in enumerate(row):draw.rectangle((40+c*40,30+r*30,79+c*40,59+r*30),fill=rgb)
        for box in ([0.2,0.25,0.8,0.75],[0.05,0.1,0.95,0.9]):
            cells=grid(image,box,2,3)['cells']
            self.assertEqual([[x['colour'] for x in row] for row in cells],[['red','olive','blue'],['green','yellow','red']])

    def test_grid_tool_returns_fixed_pixel_labels_and_marked_image(self):
        from PIL import Image,ImageDraw
        image=Image.new('RGB',(200,160),'white');draw=ImageDraw.Draw(image)
        for y,end,rgb in [(10,150,(255,140,0)),(50,60,(255,140,0)),(90,180,(0,230,20))]:draw.rectangle((20,y,end,y+19),fill=rgb)
        draw.rectangle((20,130,59,149),fill=(232,64,56));draw.rectangle((60,130,99,149),fill=(150,60,200))
        image.save(self.source/'bars.png')
        strip,png=self.workbench.call('read_grid',{'file':'bars.png','box':[.5,0,.55,.75],'rows':3,'cols':1,'snap':False})
        self.assertEqual(strip['colours'],[['orange'],['white'],['green']]);self.assertTrue(png.startswith(b'\x89PNG'))
        stem=strip['references'].split('/R<')[0];index=self.workbench.index()
        self.assertEqual([index[f'{stem}/R{r}C1'] for r in (1,2,3)],['orange','white','green'])
        self.assertEqual(self.workbench.visual[f'{stem}/R1C1']['reader'],'pixel');self.assertEqual(strip['rgb_hex'][2],['00e614'])
        cells,_=self.workbench.call('read_grid',{'file':'bars.png','box':[0,.78,.6,1],'rows':1,'cols':2})
        self.assertEqual(cells['colours'],[['red','other']]);self.assertEqual(cells['uncertain'],[[1,2]])
        grid_ref=cells['references'].split('/R<')[0]
        contract={'fields':{},'headline':{'metric':'accuracy','threshold':.5,'op':'>','records':[
            {'id':'a','score':{'ref':f'{grid_ref}/R1C1','map':{'red':1}},'truth':{'ref':f'{stem}/R1C1','map':{'orange':1,'white':0}}},
            {'id':'b','score':{'ref':f'{grid_ref}/R1C2','map':{'other':0}},'truth':{'ref':f'{stem}/R2C1','map':{'orange':1,'white':0}}}]}}
        result=self.workbench.check(contract,{'metric':'accuracy','value':1,'n':2,'tolerance':0})
        self.assertEqual([(r['score'],r['truth']) for r in result['rows']],[(1,1),(0,0)])
        self.assertEqual([e for e in result['errors'] if 'Uncertain' in e],[f'Uncertain visual label {grid_ref}/R1C2'])
        self.assertIn('read_grid',[t['function']['name'] for t in TOOLS])
        self.assertEqual(self.workbench.redact(f"cannot identify image file '{self.workbench.source}/bars.png'"),"cannot identify image file 'source/bars.png'")

    def test_tiered_price_follows_request_input_length(self):
        sets=json.loads((Path(__file__).resolve().parent/'experiment_v2.json').read_text())['model_sets']
        usage={'prompt_tokens':40000,'completion_tokens':1000,'prompt_tokens_details':{'cached_tokens':30000}}
        self.assertAlmostEqual(cost(sets['doubao']['weak'],usage),(10000*4.8+30000*.96+1000*24)/1e6)
        self.assertAlmostEqual(cost(sets['doubao']['strong'],usage),(10000*6+30000*1.2+1000*30)/1e6)
        self.assertAlmostEqual(cost(sets['qwen']['strong'],{**usage,'prompt_tokens_details':None}),(40000*12+1000*36)/1e6)

    def test_token_bound_ignores_base64_bytes_but_accounts_for_image(self):
        a=token_upper([{'content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,abc'}}]}],100)
        b=token_upper([{'content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+'x'*100000}}]}],100)
        plain=token_upper([{'content':[]}],100)
        self.assertEqual(a,b)
        self.assertEqual(a-plain,16384)

    @unittest.skipUnless(sys.platform=='darwin','macOS sandbox adapter')
    def test_sandbox_code_and_no_stale_contract(self):
        first=self.workbench.python("CONTRACT={'status':'blocked'};print(cells['table.csv/data/R1C1'])")
        self.assertEqual(first['returncode'],0);self.assertEqual(first['stdout'].strip(),'4')
        write=self.workbench.python("(scratch.parent/'visual.json').write_text('forged evidence')")
        self.assertNotEqual(write['returncode'],0)
        self.assertFalse((self.root/'scratch'/'visual.json').exists())
        second=Workbench(self.source,self.root/'scratch','fixture').python("raise ValueError('new failure')")
        self.assertNotEqual(second['returncode'],0);self.assertNotIn('contract',second)


if __name__=='__main__':unittest.main()
