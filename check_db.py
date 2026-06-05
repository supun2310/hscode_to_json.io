from pymongo import MongoClient
MONGO_URI = 'mongodb+srv://udanaravindurv_db_user:RqWgEd8CMHxb5Ttp@cluster0.huccgsz.mongodb.net/?appName=Cluster0'
client = MongoClient(MONGO_URI)
db = client['wizard']
col = db['hscodes']
print(f"Total docs in DB: {col.count_documents({})}")
print(f"Docs in chapter 20: {col.count_documents({'chapter': '20'})}")
first_doc = col.find_one({'chapter': '20'})
if first_doc:
    print(f"Sample doc hs_code: {first_doc.get('hs_code')}")
    print(f"Sample doc taxation_details: {first_doc.get('taxation_details')}")
