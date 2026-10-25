"""Optional maintainer tool: subset a Noto CJK SC OTF, retaining OFL notices.
Usage: python tools/subset_font.py full-source.otf assets/MaoyuSans.otf
Requires fonttools only when rebuilding the font, not at runtime.
"""
import sys
from fontTools import subset
from fontTools.ttLib import TTFont

if __name__=='__main__':
    source,destination=sys.argv[1:]
    font=TTFont(source)
    opts=subset.Options();opts.layout_features=[];opts.name_IDs=['*'];opts.name_legacy=True;opts.name_languages=['*']
    cutter=subset.Subsetter(options=opts)
    ranges=[(0x20,0x024F),(0x2000,0x206F),(0x2190,0x21FF),(0x2500,0x27BF),
            (0x3000,0x30FF),(0x3400,0x4DBF),(0x4E00,0x9FFF),(0xFF00,0xFFEF)]
    cutter.populate(unicodes={cp for low,high in ranges for cp in range(low,high+1)})
    cutter.subset(font)
    for rec in font['name'].names:
        new={1:'Maoyu UI Sans',2:'Regular',3:'MaoyuUISans-Regular-1.1',4:'Maoyu UI Sans Regular',6:'MaoyuUISans-Regular',16:'Maoyu UI Sans',17:'Regular'}.get(rec.nameID)
        if new is not None:rec.string=new.encode(rec.getEncoding(),errors='replace')
    if 'CFF ' in font:
        cff=font['CFF '].cff;cff.fontNames=['MaoyuUISans-Regular']
        cff.topDictIndex[0].FullName='Maoyu UI Sans Regular';cff.topDictIndex[0].FamilyName='Maoyu UI Sans'
    font.save(destination)
