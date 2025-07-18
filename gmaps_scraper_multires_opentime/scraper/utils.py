# utils.py 可以加入像是檢查API限額、資料清洗等函數
def clean_text(text):
    return text.replace("\n", " ").strip()
