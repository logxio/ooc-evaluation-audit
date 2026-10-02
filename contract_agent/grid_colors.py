"""Read a coloured grid, heat map or bar-chart strip without a model: sample each cell centre, name the colour."""
import argparse
import colorsys
import json
from pathlib import Path
import statistics


def load(path,page=None,scale=4):
    from PIL import Image
    path=Path(path)
    if path.suffix.lower()=='.pdf':
        import pypdfium2
        return pypdfium2.PdfDocument(path)[(page or 1)-1].render(scale=scale).to_pil().convert('RGB')
    return Image.open(path).convert('RGB')


def colour(rgb):
    h,l,s=colorsys.rgb_to_hls(*[v/255 for v in rgb]);h*=360
    if l>0.93:return 'white'
    if s<0.15:return 'white' if l>0.85 else ('grey' if l>0.25 else 'black')
    if 35<=h<=70:return 'olive' if s<0.5 else 'yellow'
    if 15<h<35:return 'orange'
    if h<=15 or h>=340:return 'pink' if l>0.75 else 'red'
    if 80<=h<=170:return 'green'
    if 180<=h<=260:return 'lavender' if l>0.8 else ('light blue' if l>0.6 else 'blue')
    return 'other'


def grid(image,box,rows,cols,snap=True,fill=0.8):
    """box: fractions [left, top, right, bottom] of the image. snap=True finds the filled cell block inside the box
    (heat maps, filled grids; a loose box is fine); snap=False takes the box itself as the grid (strips across bars where some cells are empty)."""
    px=image.load();W,H=image.size;x0,y0,x1,y1=[round(f*n) for f,n in zip(box,(W,H,W,H))]
    if not (0<=x0<x1<=W and 0<=y0<y1<=H):raise ValueError('The box must lie inside the image with left<right and top<bottom')
    if rows<1 or cols<1 or rows*cols>2000:raise ValueError('Rows and columns must be positive, at most 2000 cells')
    if snap:
        # Cell fill is anything neither near-white paper nor near-black text and rules. Pixel lines filled almost as fully as
        # the fullest one form runs; runs closer than a typical run are one block, and the block with most such lines is the
        # grid, so labels, legends and margins inside a loose box drop out.
        def filled(c):return min(c)<=235 and max(c)>=60
        def edges(counts,start):
            peak=max(counts)
            if not peak:raise ValueError('No filled cells inside the box; use snap=false for partly empty strips')
            hits=[start+i for i,n in enumerate(counts) if n>=fill*peak];runs=[[hits[0],hits[0]]]
            for h in hits[1:]:
                if h==runs[-1][1]+1:runs[-1][1]=h
                else:runs.append([h,h])
            size=statistics.median(b-a+1 for a,b in runs);blocks=[runs[0]]
            for a,b in runs[1:]:
                if a-blocks[-1][1]-1<=size:blocks[-1]=[blocks[-1][0],b]
                else:blocks.append([a,b])
            return max(blocks,key=lambda k:sum(k[0]<=h<=k[1] for h in hits))
        top,bottom=edges([sum(filled(px[x,y]) for x in range(x0,x1,2)) for y in range(y0,y1)],y0)
        left,right=edges([sum(filled(px[x,y]) for y in range(top,bottom+1,2)) for x in range(x0,x1)],x0)
    else:left,top,right,bottom=x0,y0,x1-1,y1-1
    cw=(right-left+1)/cols;rh=(bottom-top+1)/rows;cells=[]
    for r in range(rows):
        row=[]
        for c in range(cols):
            cx,cy=int(left+(c+.5)*cw),int(top+(r+.5)*rh);d=max(1,int(min(cw,rh)/6))
            pts=[px[min(W-1,max(0,cx+dx)),min(H-1,max(0,cy+dy))] for dx in (-d,0,d) for dy in (-d,0,d)]
            rgb=tuple(int(statistics.median(p[k] for p in pts)) for k in range(3))
            row.append({'colour':colour(rgb),'rgb':rgb,'xy':[cx,cy]})
        cells.append(row)
    return {'grid_px':[left,top,right,bottom],'cell_px':[round(cw,1),round(rh,1)],'cells':cells}


def overlay(image,result,pad=12):
    """The grid area with every sample point marked, upscaled when small, so a reader can check the alignment."""
    from PIL import Image,ImageDraw
    left,top,right,bottom=result['grid_px'];ox,oy=max(0,left-pad),max(0,top-pad)
    crop=image.crop((ox,oy,min(image.width,right+pad+1),min(image.height,bottom+pad+1))).copy();draw=ImageDraw.Draw(crop)
    for row in result['cells']:
        for cell in row:
            x,y=cell['xy'][0]-ox,cell['xy'][1]-oy;draw.ellipse((x-2,y-2,x+2,y+2),outline='black',fill='white')
    if crop.width<800:crop=crop.resize((800,max(1,round(crop.height*800/crop.width))),Image.NEAREST)
    crop.thumbnail((2400,2400));return crop


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--page',type=int)
    p.add_argument('--box',type=float,nargs=4,required=True);p.add_argument('--rows',type=int,required=True);p.add_argument('--cols',type=int,required=True)
    p.add_argument('--exact',action='store_true',help='Use the box itself as the grid instead of snapping to the coloured block')
    p.add_argument('--fill',type=float,default=0.8,help='Share of a pixel line that must be coloured to belong to a snapped grid')
    a=p.parse_args();result=grid(load(a.source,a.page),a.box,a.rows,a.cols,not a.exact,a.fill)
    print(json.dumps({**result,'cells':[[c['colour'] for c in row] for row in result['cells']]},indent=1))


if __name__=='__main__':main()
