from uuid import uuid4
from sqlalchemy import select
from .db import Session, Model, Dataset, Prompt

def seed():
    with Session() as db:
        if db.scalar(select(Model.id).limit(1)):
            return
        for model, name in [('demo-stable', 'Demo / Stable'), ('demo-experimental', 'Demo / Experimental')]:
            db.add(Model(id=str(uuid4()), name=name, provider='demo', model=model, endpoint='', secret=''))
        rows = [
            ('基礎算術', '請只回答：2 + 2 等於多少？', 'exact', '4'),
            ('地理知識', '法國的首都是哪裡？', 'contains', '巴黎'),
            ('結構化輸出', '請輸出 JSON，包含 name 字串與 age 整數。', 'json_schema', ''),
            ('程式知識', '請用一句話說明 Python。', 'contains', '程式語言'),
            ('英文翻譯', '翻譯「你好」為英文，只輸出一個單字。', 'exact', 'Hello'),
            ('科學常識', '水的化學式是什麼？', 'exact', 'H2O'),
            ('序列排序', '排序 3, 1, 2，使用逗號與空格分隔。', 'exact', '1, 2, 3'),
            ('亞洲地理', '日本首都是哪裡？', 'contains', '東京'),
            ('布林輸出', '請以布林值表示真，只輸出 true 或 false。', 'exact', 'true'),
            ('文字摘要', '摘要：這個平台可執行題库、比較模型回答、檢查品質並量測效能。', 'manual', ''),
        ]
        cases = [{'title': title, 'messages': [{'role': 'user', 'content': question}], 'tags': ['示範'], 'rule': {'kind': kind, 'expected': expected, 'schema': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'age': {'type': 'integer'}}, 'required': ['name', 'age']} if kind == 'json_schema' else {}}} for title, question, kind, expected in rows]
        db.add(Dataset(id=str(uuid4()), name='入門評估 · 10 題', cases=cases))
        db.add(Prompt(id=str(uuid4()), name='通用助理 v1', text='你是一位精確、簡潔的助理。請遵循使用者指定的格式回答。'))
        db.commit()
