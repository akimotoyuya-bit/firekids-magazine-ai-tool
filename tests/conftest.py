import sys
from pathlib import Path

# article_generator を import パスに追加（app.py 自身も同じ sys.path ハックを持つ）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "article_generator"))
