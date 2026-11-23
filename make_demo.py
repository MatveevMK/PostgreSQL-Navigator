"""Generate synthetic metadata; never reads workplace files."""
from pathlib import Path
import pandas as pd

def main():
    folder = Path(__file__).resolve().parent / 'data'
    folder.mkdir(exist_ok=True)
    columns = []
    for table, fields in {'customers': ['id', 'name'], 'orders': ['id', 'customer_id', 'created_at'], 'order_items': ['id', 'order_id', 'quantity']}.items():
        for field in fields:
            columns.append(['demo', table, field, 'text' if field == 'name' else 'integer', 'NO'])
    pd.DataFrame(columns, columns=['table_schema','table_name','column_name','data_type','is_nullable']).to_excel(folder / 'demo_первый.xlsx', index=False)
    pd.DataFrame([
        ['demo','orders','customer_id','demo','customers','id'],
        ['demo','order_items','order_id','demo','orders','id'],
    ], columns=['child_schema','child_table','child_column','parent_schema','parent_table','parent_column']).to_excel(folder / 'demo_второй.xlsx', index=False)

if __name__ == '__main__':
    main()
