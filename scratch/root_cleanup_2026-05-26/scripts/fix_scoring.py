from pathlib import Path
import re

# Fix scoring.py
scoring_file = Path(".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/scoring.py")
content = scoring_file.read_text(encoding="utf-8")
content = content.replace(',"speed_rating_score"', '')
# We need to re-adjust MATRIX_WEIGHTS in scoring.py as well
# Original: MATRIX_WEIGHTS = {"stability":0.18,"sectional":0.14,"race_shape":0.09,"jockey_trainer":0.16,"class_weight":0.06,"track":0.13,"form_line":0.17,"speed_performance":0.07}
# Sectional absorbs speed_performance (0.14 + 0.07 = 0.21)
content = content.replace('"sectional":0.14', '"sectional":0.21')
content = content.replace(',"speed_performance":0.07', '')
scoring_file.write_text(content, encoding="utf-8")

# Fix matrix_mapper.py
mapper_file = Path(".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/matrix_mapper.py")
content = mapper_file.read_text(encoding="utf-8")
content = re.sub(r'\s+"speed_performance": \([\s\S]*?\),', '', content)
mapper_file.write_text(content, encoding="utf-8")
