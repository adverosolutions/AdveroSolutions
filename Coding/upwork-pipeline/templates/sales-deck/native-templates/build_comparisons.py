#!/usr/bin/env python3
"""Compose review sheets from existing UI captures; Pillow required."""
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parent.parent
PAIRS=[
 ('ghl','visual-reference/assets/ghl-workflow-a40574215114.png','native-templates/qa/ghl-workflow-native.png','Vendor Workflow Builder reference'),
 ('n8n','visual-reference/assets/n8n-current-editor-f118523d2bb0.png','native-templates/qa/n8n-inspector-normalize.png','Official Edit Fields node detail'),
 ('zapier','visual-reference/assets/zapier-quickstart-4d70d16cfc8f.png','native-templates/qa/zapier-test-native.png','Official older visual Zap canvas; current panel gap'),
 ('claude','native-templates/references/claude-skill-detail-current.png','native-templates/qa/claude-skills-native.png','Installed current dark Skills detail'),
 ('claude-project','native-templates/references/claude-project-wide-current.png','native-templates/qa/claude-project-native.png','Installed example project, narrow left column'),
 ('ghl-pipeline','native-templates/references/ghl-card-config-6.png','native-templates/qa/ghl-pipeline-native.png','Vendor customized default card, labels and values')]
for key,ref,current,label in PAIRS:
    sheet=Image.new('RGB',(1600,700),'#edf2f8');draw=ImageDraw.Draw(sheet)
    for x,p,title in [(0,ref,label),(800,current,'Rebuilt candidate, controlled viewport')]:
        draw.text((x+22,20),title,fill='#26374e');im=Image.open(ROOT/p).convert('RGB');thumb=ImageOps.contain(im,(760,610));sheet.paste(thumb,(x+20+(760-thumb.width)//2,55+(610-thumb.height)//2))
    draw.text((20,679),'Aspect ratios preserved. Different source viewports; visual comparison only, not a pixel-parity claim.',fill='#657185')
    sheet.save(ROOT/'native-templates/qa'/(key+'-comparison.png'))
print('Six bounded source-versus-render comparisons saved')
