from __future__ import annotations
import json, os, struct, zlib, hashlib
from dataclasses import dataclass
from typing import Iterable, Sequence

RGBA = tuple[int,int,int,int]

def hx(s:str, a:int=255)->RGBA:
    s=s.lstrip('#')
    return (int(s[0:2],16),int(s[2:4],16),int(s[4:6],16),a)

TRANSPARENT=(0,0,0,0)

class Canvas:
    def __init__(self,w:int,h:int,color:RGBA=TRANSPARENT):
        self.w=w; self.h=h; self.p=[color]*(w*h)
    def set(self,x:int,y:int,c:RGBA):
        if 0<=x<self.w and 0<=y<self.h: self.p[y*self.w+x]=c
    def get(self,x:int,y:int)->RGBA:
        return self.p[y*self.w+x] if 0<=x<self.w and 0<=y<self.h else TRANSPARENT
    def rect(self,x:int,y:int,w:int,h:int,c:RGBA):
        for yy in range(max(0,y),min(self.h,y+h)):
            o=yy*self.w
            for xx in range(max(0,x),min(self.w,x+w)): self.p[o+xx]=c
    def line(self,x0:int,y0:int,x1:int,y1:int,c:RGBA):
        dx=abs(x1-x0); sx=1 if x0<x1 else -1
        dy=-abs(y1-y0); sy=1 if y0<y1 else -1
        err=dx+dy
        while True:
            self.set(x0,y0,c)
            if x0==x1 and y0==y1: break
            e2=2*err
            if e2>=dy: err+=dy; x0+=sx
            if e2<=dx: err+=dx; y0+=sy
    def poly(self,pts:Sequence[tuple[int,int]],c:RGBA):
        if len(pts)<3:return
        miny=max(0,min(y for _,y in pts)); maxy=min(self.h-1,max(y for _,y in pts))
        n=len(pts)
        for y in range(miny,maxy+1):
            scan_y=y+0.5; xs=[]
            for i in range(n):
                x1,y1=pts[i]; x2,y2=pts[(i+1)%n]
                if (y1<=scan_y<y2) or (y2<=scan_y<y1):
                    t=(scan_y-y1)/(y2-y1); xs.append(x1+t*(x2-x1))
            xs.sort()
            for i in range(0,len(xs)-1,2):
                a=max(0,int(xs[i]+0.999999)); b=min(self.w-1,int(xs[i+1]-1e-9))
                for x in range(a,b+1): self.set(x,y,c)
    def blit(self,src:'Canvas',x:int,y:int):
        for sy in range(src.h):
            for sx in range(src.w):
                c=src.get(sx,sy)
                if c[3]: self.set(x+sx,y+sy,c)
    def scale(self,k:int)->'Canvas':
        out=Canvas(self.w*k,self.h*k)
        for y in range(self.h):
            for x in range(self.w): out.rect(x*k,y*k,k,k,self.get(x,y))
        return out


def chunk(tag:bytes,data:bytes)->bytes:
    return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)

def write_png(path:str,cv:Canvas):
    raw=bytearray()
    for y in range(cv.h):
        raw.append(0)
        for x in range(cv.w): raw.extend(cv.get(x,y))
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',cv.w,cv.h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(raw),9))+chunk(b'IEND',b'')
    with open(path,'wb') as f:f.write(png)

def outline_mask(cv:Canvas,color:RGBA, radius:int=1):
    src=[px[3]>0 for px in cv.p]
    add=[]
    for y in range(cv.h):
        for x in range(cv.w):
            if src[y*cv.w+x]: continue
            found=False
            for oy in range(-radius,radius+1):
                for ox in range(-radius,radius+1):
                    if abs(ox)+abs(oy)>radius: continue
                    nx=x+ox; ny=y+oy
                    if 0<=nx<cv.w and 0<=ny<cv.h and src[ny*cv.w+nx]: found=True; break
                if found: break
            if found:add.append((x,y))
    for x,y in add:cv.set(x,y,color)

# Cozy palette
C={
 'outline':hx('#2a1e1a'), 'shadow':hx('#281d1a',90),
 'skin_d':hx('#a9654e'), 'skin':hx('#d99a75'), 'skin_h':hx('#f0bd96'),
 'hair_d':hx('#3b241f'), 'hair':hx('#5a3428'), 'hair_h':hx('#7c4b35'),
 'shirt':hx('#f0ddba'), 'shirt_s':hx('#c6aa7d'),
 'coat_d':hx('#345746'), 'coat':hx('#4f7a62'), 'coat_h':hx('#75a07d'),
 'scarf_d':hx('#9b4c2e'), 'scarf':hx('#d8783d'), 'scarf_h':hx('#f0a75f'),
 'pants_d':hx('#263945'), 'pants':hx('#385464'), 'pants_h':hx('#557383'),
 'boot_d':hx('#3a2821'), 'boot':hx('#5d3e2e'),
 'bag_d':hx('#5d3727'), 'bag':hx('#8b5839'), 'bag_h':hx('#b37b50'),
 'book_d':hx('#324b56'), 'book':hx('#4d7080'), 'paper':hx('#ead7a8'),
 'eye':hx('#2b2320'), 'glasses':hx('#3b4a50'),
}

def rr(cv:Canvas,x:int,y:int,w:int,h:int,fill:RGBA,outline:RGBA|None=C['outline']):
    if outline:
        cv.rect(x-1,y,w+2,h,outline); cv.rect(x,y-1,w,h+2,outline)
    cv.rect(x,y,w,h,fill)

def draw_shadow(cv:Canvas,cx:int=16):
    cv.rect(cx-7,43,14,2,C['shadow']); cv.rect(cx-5,42,10,1,C['shadow'])

def draw_face_down(cv:Canvas, bob:int):
    # hair mass behind face
    rr(cv,9,5+bob,14,10,C['hair'])
    cv.rect(10,5+bob,12,2,C['hair_h'])
    cv.rect(8,8+bob,3,7,C['hair_d']); cv.rect(21,8+bob,3,7,C['hair_d'])
    # face
    rr(cv,11,8+bob,10,9,C['skin'])
    cv.rect(12,8+bob,8,2,C['skin_h']); cv.rect(11,14+bob,10,3,C['skin_d'])
    cv.set(13,12+bob,C['eye']); cv.set(18,12+bob,C['eye'])
    cv.rect(12,11+bob,3,1,C['glasses']); cv.rect(17,11+bob,3,1,C['glasses']); cv.set(16,11+bob,C['glasses'])
    # bangs
    cv.rect(10,7+bob,4,3,C['hair']); cv.rect(18,7+bob,4,3,C['hair']); cv.rect(14,6+bob,4,2,C['hair_h'])

def draw_body_down(cv:Canvas,phase:int,bob:int):
    # legs behind body
    if phase==1:
        rr(cv,10,34+bob,5,8,C['pants']); rr(cv,18,33+bob,5,9,C['pants_d'])
        rr(cv,9,41+bob,6,3,C['boot']); rr(cv,18,41+bob,6,3,C['boot_d'])
    elif phase==3:
        rr(cv,9,33+bob,5,9,C['pants_d']); rr(cv,17,34+bob,5,8,C['pants'])
        rr(cv,8,41+bob,6,3,C['boot_d']); rr(cv,17,41+bob,6,3,C['boot'])
    else:
        rr(cv,10,34+bob,5,8,C['pants']); rr(cv,17,34+bob,5,8,C['pants_d'])
        rr(cv,9,41+bob,6,3,C['boot']); rr(cv,17,41+bob,6,3,C['boot'])
    # arms
    swing={0:0,1:-1,2:0,3:1}[phase]
    rr(cv,7,22+bob+swing,5,12,C['coat_d']); cv.rect(8,23+bob+swing,2,8,C['coat'])
    rr(cv,20,22+bob-swing,5,12,C['coat']); cv.rect(21,23+bob-swing,2,8,C['coat_h'])
    # hands
    rr(cv,8,32+bob+swing,3,3,C['skin']); rr(cv,21,32+bob-swing,3,3,C['skin'])
    # torso cardigan
    rr(cv,10,19+bob,12,17,C['coat'])
    cv.rect(11,20+bob,3,14,C['coat_h']); cv.rect(19,20+bob,2,14,C['coat_d'])
    cv.rect(15,20+bob,2,15,C['shirt']); cv.rect(16,20+bob,1,15,C['shirt_s'])
    # scarf embedded into outfit, not a detached badge
    cv.rect(11,18+bob,10,3,C['scarf_d']); cv.rect(12,18+bob,8,2,C['scarf']); cv.rect(17,20+bob,3,7,C['scarf']); cv.rect(18,21+bob,1,4,C['scarf_h'])
    # satchel strap and bag
    cv.line(11,21+bob,21,33+bob,C['bag_d']); cv.line(12,21+bob,22,33+bob,C['bag_h'])
    rr(cv,20,29+bob,6,8,C['bag']); cv.rect(21,30+bob,4,2,C['bag_h'])
    # notebook in left hand
    rr(cv,5,29+bob+swing,5,7,C['book']); cv.rect(6,30+bob+swing,3,4,C['paper']); cv.set(7,31+bob+swing,C['book_d'])

def draw_cozy_down(phase:int)->Canvas:
    cv=Canvas(32,48); bob=0 if phase in (0,2) else -1
    draw_shadow(cv)
    draw_body_down(cv,phase,bob)
    draw_face_down(cv,bob)
    return cv

def draw_cozy_up(phase:int)->Canvas:
    cv=Canvas(32,48); bob=0 if phase in (0,2) else -1; draw_shadow(cv)
    # legs
    if phase==1:
        rr(cv,10,34+bob,5,8,C['pants']); rr(cv,18,33+bob,5,9,C['pants_d'])
    elif phase==3:
        rr(cv,9,33+bob,5,9,C['pants_d']); rr(cv,17,34+bob,5,8,C['pants'])
    else:
        rr(cv,10,34+bob,5,8,C['pants']); rr(cv,17,34+bob,5,8,C['pants_d'])
    rr(cv,9,41+bob,6,3,C['boot']); rr(cv,17,41+bob,6,3,C['boot'])
    swing={0:0,1:-1,2:0,3:1}[phase]
    rr(cv,7,22+bob+swing,5,12,C['coat_d']); rr(cv,20,22+bob-swing,5,12,C['coat'])
    rr(cv,10,19+bob,12,17,C['coat'])
    cv.rect(11,20+bob,3,14,C['coat_h']); cv.rect(19,20+bob,2,14,C['coat_d'])
    # satchel strap/bag from back
    cv.line(11,20+bob,22,32+bob,C['bag_d']); cv.line(12,20+bob,23,32+bob,C['bag_h'])
    rr(cv,20,29+bob,6,8,C['bag']); cv.rect(21,30+bob,4,2,C['bag_h'])
    # hair/back head
    rr(cv,9,5+bob,14,12,C['hair']); cv.rect(10,5+bob,12,2,C['hair_h']); cv.rect(9,13+bob,14,4,C['hair_d'])
    cv.rect(12,15+bob,8,3,C['scarf_d']); cv.rect(13,15+bob,6,2,C['scarf'])
    return cv\n\ndef draw_cozy_side(phase:int,right:bool)->Canvas:\n    cv=Canvas(32,48); bob=0 if phase in (0,2) else -1; draw_shadow(cv)\n    # helper mirror x coordinate/rect\n    def X(x,w=1): return 32-x-w if right else x\n    def R(x,y,w,h,fill,outline=C['outline']): rr(cv,X(x,w),y,w,h,fill,outline)\n    def P(x,y,col): cv.set(X(x),y,col)\n    # far leg then near leg\n    if phase==1:\n        R(14,34+bob,5,8,C['pants_d']); R(11,33+bob,5,9,C['pants'])\n        R(14,41+bob,6,3,C['boot_d']); R(9,41+bob,7,3,C['boot'])\n    elif phase==3:\n        R(11,34+bob,5,8,C['pants_d']); R(15,33+bob,5,9,C['pants'])\n        R(9,41+bob,7,3,C['boot_d']); R(15,41+bob,7,3,C['boot'])\n    else:\n        R(12,34+bob,5,8,C['pants']); R(16,34+bob,5,8,C['pants_d'])\n        R(11,41+bob,6,3,C['boot']); R(16,41+bob,6,3,C['boot_d'])\n    # back arm\n    swing={0:0,1:-1,2:0,3:1}[phase]\n    R(17,22+bob-swing,5,12,C['coat_d']); R(18,32+bob-swing,3,3,C['skin'])\n    # torso\n    R(11,19+bob,11,17,C['coat']);\n    cv.rect(X(12,3),20+bob,3,14,C['coat_h']); cv.rect(X(19,2),20+bob,2,14,C['coat_d'])\n    # scarf tail\n    R(12,18+bob,9,3,C['scarf']); R(13,20+bob,3,7,C['scarf_d'])\n    # near arm holding notebook\n    R(8,22+bob+swing,5,12,C['coat']); R(9,32+bob+swing,3,3,C['skin'])\n    R(5,28+bob+swing,5,8,C['book']); cv.rect(X(6,3),29+bob+swing,3,5,C['paper'])\n    # satchel behind\n    R(19,28+bob,6,9,C['bag']); cv.rect(X(20,4),29+bob,4,2,C['bag_h'])\n    # face/hair profile\n    R(10,5+bob,13,11,C['hair']); cv.rect(X(10,10),5+bob,10,2,C['hair_h']); R(9,8+bob,4,8,C['hair_d'])\n    R(11,8+bob,9,9,C['skin']); cv.rect(X(12,7),8+bob,7,2,C['skin_h']); cv.rect(X(1,9),14+bob,9,3,C['skin_d'])\n    P(12,12+bob,C['eye']); cv.rect(X(11,4),11+bob,4,1,C['glasses'])\n    # nose pixel toward front\n    P(10,13+bob,C['skin_h'])\n    cv.rect(X(1,3),7%+bob,3,4,C['hair']); cv.rect(X(16,5),6+bib,5,3,C['hair_h'])\n    return cv\n\ndef make_cozy_sheet()->Canvas;\n    sheet=Canvas(32*4,48*4)\n    rows=[lambda p:draw_cozy_down(p),lambda p:draw_cozy_side(p,False),lambda p:draw_cozy_side(p,True),lambda p:draw_cozy_up(p)]\n    for r,fn in enumerate(rows):\n        for col in range(4): sheet.blit(fn(col),col*32,r*48)\n    return sheet\n\n# Industrial palette and role accents\nM={\n 'outline':hx('#151a20'), 'outline2':hx('#20262d'),\n 'dark':hx('#303843'), 'mid':hx('#505b67'), 'metal':hx('#737f89'), 'light':hx('#a5b1b8'), 'shine':hx('#d7e0e3'),\n 'void':hx('#0a0e12'), 'shadow':hx('#11161b',110),\n}\nACCENTS={\n 'research':(hx('#55d6ff'),hx('#b8efff'),hx('#16536a')),\n 'coder':(hx('#ffb347'),hx('#ffe09a'),hx('#6e3b17')),\n 'browser':(hx('#8be38b'),hx('#d6ffd2'),hx('#235a38')),\n 'memory':(hx('b493ff'),hx('#e3d6ff'),hx('#463177')),\n 'approval':(hx('#ff6f7f'),hx('#ffc4cb'),hx('#6f2231')),\n 'runtime':(hx('#ffd84d'),hx('#fff2a4'),hx('#6a5415')),\n}\n\ndef pix_outline(cv:Canvas):\n    outline_mask(cv,M['outline'],1)\n\ndef diamond(cv:Canvas,cx:int,cy:int,rx:int,ry:int,c:RGBA):\n    cv.poly([(cx,cy-ry),(cx+rx,cy),(cx,cy+ry),(cx-rx,cy)],c)\n\ndef draw_core(cv:Canvas,cx:int,cy:int,a:RGBA,ah:RGBA,ad:RGBA):\n    diamond(cv,cx,cy,5,5,ad); diamond(cv,cx,cy-1,4,4,a); cv.rect(cx-1,cy-3,2,2,ah); cv.rect(cx-1,cy+2,2,1,M['void'])\n\ndef make_unit(role:str)->Canvas:\n    cv=Canvas(32,32); a,ah,ad=ACCENTS[role]\n    # render body without outline, then outline once for clean silhouette\n    if role=='research':\n        # wide sensor craft with antenna prongs\n        diamond(cv,16,16,10,8,M['mid']); diamond(cv,16,15,8,6,M['metal'])\n        cv.rect(4,14,6,4,M['dark']); cv.rect(22,14,6,4,M['dark'])\n        cv.rect(6,10,2,5,M['metal']); cv.rect(24,10,2,5,M['metal']); cv.rect(5,8,4,2,M['light']); cv.rect(23,8,4,2,M['light'])\n        cv.rect(14,5,4,5,M['dark']); cv.rect(15,3,2,4,a); cv.set(15,2,ah); cv.set(16,2,ah)\n        draw_core(cv,16,16,a,ah,ad)\n    elif role=='coder':\n        # angular forge chassis, two tool arms\n        cv.rect(8,9,16,15,M['dark']); cv.rect(10,7,12,16,M['mid']); cv.rect(12,8,8,13,M['metal'])\n        cv.poly([(8,12),(4,9),(3,11),(7,16)],M['metal']); cv.poly([(24,12),(28,9),(29,11),(25,16)],M['metal'])\n        cv.rect(3,8,4,3,M['light']); cv.rect(25,8,4,3,M['light'])\n        cv.rect(8,22,5,5,M['dark']); cv.rect(19,22,5,5,M['dark'])\n        draw_core(cv,16,15,a,ah,ad)\n        cv.rect(14,23,4,3,a); cv.rect(15,23,2,1,ah)\n    elif role=='browser':\n        # circular scout with orbit ring and fins\n        diamond(cv,16,16,11,9,M['dark']); diamond(cv,16,16,9,7,M['mid']); diamond(cv,16,15,7,5,M['metal'])\n        cv.rect(3,14,6,4,M['light']); cv.rect(23,14,6,4,M['light']); cv.rect(6,11,3,2,M['dark']); cv.rect(23,11,3,2,M['dark'])\n        cv.rect(14,5,4,4,M['dark']); cv.rect(15,4,2,3,a)\n        draw_core(cv,16,16,a,ah,ad)\n        cv.set(5,12,ah); cv.set(26,12,ah)\n    elif role=='memory':\n        # stacked archive plates\n        cv.rect(7,8,18,5,M['dark']); cv.rect(9,6,14,5,M['metal']); cv.rect(6,14,20,5,M['dark']); cv.rect(8,12,16,5,M['mid'])\n        cv.rect(7,20,18,5,M['dark']); cv.rect(9,18,14,5,M['metal'])\n        cv.rect(11,7,10,2,M['light']); cv.rect(10,13,12,2,M['light']); cv.rect(11,19,10,2,M['light'])\n        draw_core(cv,16,15,a,ah,ad)\n    elif role=='approval':\n        # shield/gate unit with twin locking arms\n        cv.poly([(16,5),(25,9),(24,21),(16,27),(8,21),(7,9)],M['dark'])\n        cv.poly([(16,7),(22,10),(21,19),(16,23),(11,19),(10,10)],M['metal'])\n        cv.rect(3,13,6,6,M['mid']); cv.rect(23,13,6,6,M['mid']); cv.rect(4,14,4,4,M['light']); cv.rect(24,14,4,4,M['light'])\n        draw_core(cv,16,15,a,ah,ad)\n        cv.rect(14,21,4,3,ad); cv.rect(15,21,2,2,a)\n    elif role=='runtime':\n        # three-pronged execution unit\n        diamond(cv,16,15,8,7,M['mid']); diamond(cv,16,14,6,5,M['metal'])\n        cv.poly([(12,18),(6,26),(9,27),(15,20)],M['dark']); cv.poly([(20,18),(26,26),(23,27),(17,20)],M['dark'])\n        cv.poly([(16,19),(14,28),(18,28)],M['dark'])\n        cv.rect(5,24,5,3,M['light']); cv.rect(22,24,5,3,M['light']); cv.rect(14,26,4,3,M['light'])\n        cv.rect(14,4,4,5,M['dark']); cv.rect(15,3,2,4,a)\n        draw_core(cv,16,15,a,ah,ad)\n    pix_outline(cv)\n    # restore selected highlights after outline where desired\n    return cv\n\ndef make_industrial_sheet()->Canvas;\n    roles=['research','coder','browser','memory','approval','runtime']\n    sheet=Canvas(32*3,32*2)\n    for i,role in enumerate(roles): sheet.blit(make_unit(role),(i%3)*32,(i//3)*32)\n    return sheet\n\n# Preview composition (project review only, not production sprite data)\ndef checker(cv:Canvas,cell:int=8,c1:RGBA=hx('#17202a'),c2:RGBA=hx('#1d2935')):\n    for y in range(0,cv.h,cell):\n        for x in range(0,cv.w,cell): cv.rect(x,y,cell,cell,c1 if ((x//cell+y//cell)%2==0) else c2)\n\ndef make_preview(cozy:Canvas,industrial:Canvas)->Canvas;\n    out=Canvas(1200,720,hx('#111820'))\n    # two panels\n    out.rect(20,20,560,680,hx('#1b2530')); out.rect(600,20,580,680,hx('#171d24'))\n    # simple pixel headings as bars, labels will be in accompanying manifest; avoid anti-aliased text\n    out.rect(42,44,10,10,hx('#d8783d')); out.rect(58,44,130,10,hx('#f0ddba'))\n    out.rect(622,44,10,10,hx('#55d6ff')); out.rect(638,44,150,10,hx('#a5b1b8'))\n    # cozy sheet enlarged 3x\n    cozy_big=cozy.scale(3); out.blit(cozy_big,42,82)\n    # frame legend blocks by direction/phase\n    for rcol in enumerate([C['scarf'],C['coat_h'],C['book'],C['hair_h']]): out.rect(44,670-r*12,120,6,col)\n    # industrial sheet enlarged 5x\n    ind_big=industrial.scale(5); out.blit(ind_big,650,110)\n    # show individual icons on dark tiles, extra spacing\n    roles=['research','coder','browser','memory','approval','runtime']\n    for i,role in enumerate(roles):\n        x=628+(i%3)*178; y=470+(i//3)*108\n        out.rect(x,y,160,94,hx('#222b35')); out.rect(x+8,y+8,8,8,ACCENTS[role][0]); out.rect(x+22,y+8,76,8,M['light'])\n        unit=make_unit(role).scale(2); out.blit(unit,x+48,y+22)\n    return out\n\ndef sha(path:str)->str:\n    h=hashlib.sha256(); h.update(open(path,'rb').read()); return h.hexdigest()\n\ndef main(outdir:str):\n    os.makedirs(outdir,exist_ok=True)\n    cozy=make_cozy_sheet(); industrial=make_industrial_sheet(); preview=make_preview(cozy,industrial)\n    paths={\n     'cozy':os.path.join(outdir,'cozy-research-agent-v0.png'),\n      'industrial':os.path.join(outdir,'industrial-agent-units-v0.png'),\n      'preview':os.path.join(outdir,'dual-agent-art-assets-v0-preview.png'),\n    }\n    write_png(paths['cozy'],cozy); write_png(paths['industrial'],industrial); write_png(paths['preview'],preview)\n    manifest={\n      'schemaVersion':'spatial-agent-art-assets/v0',\n      'generatedBy':'scripts/generate_spatial_agent_art_assets.py',\n      'license':'PROJECT_OWNED',\n      'provenance':'first_party',\n      'externalProductionAssets':[],\n      'tracks':[\n        {'id':'cozy-research-agent-v0','mode':'full-character','file':os.path.basename(paths['cozy']),'frame':{'width':32,'height':48},'columns':4,'rows':4,'directions':['south','west','east','north'],'hases':['idle','step-a','passing','step-b'],'identityEncoding':['silhouette','hair','coat','scarf','satchel','notebook'],'detachedBadge':False},\n        {'id':'industrial-agent-units-v0','mode':'complete-unit','file':os.path.basename(paths['industrial']),'frame':{'width':32,'height':32},'columns':3,'rows':2,'roles':['research','coder','browser','memory','approval','runtime'],'identityEncoding':['chassis','core','tool-module','accent-ramp'],'humanBody':False,'detachedBadge':False},\n      ],\n      'sha256':{k:sha(v) for k,v in paths.items()},\n      'references':[\n        {'repository':'BenCreating/LPC-Spritesheet-Generator','adoption':'animation/layer/palette/provenance method only','assetsCopied':False},\n        {'repository':'Anuken/Mindustry','adoption':'modular chassis/core/outline/generated-icon method only','assetsCopied':False},\n      ],\n    }\n    with open(os.path.join(outdir,'dual-agent-art-assets-v0.manifest.json'),'w',encoding='utf-8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)\n    print(json.dumps(manifest,ensure_ascii=False,indent=2))\n\nif __name__=='__main__': main(os.environ.get('OUTDIR','/mnt/data/spatial-dual-agent-art-v0'))\
