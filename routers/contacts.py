from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import csv
import io
from urllib.parse import quote

from models import SessionLocal, OrgContact
from contact_manager import generate_vcard, generate_vcard_qrcode

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

class ContactCreate(BaseModel):
    org_name: str
    org_tax_id: Optional[str] = ""
    contact_name: Optional[str] = ""
    title: Optional[str] = ""
    phone: Optional[str] = ""
    mobile: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    department: Optional[str] = ""
    tags: Optional[str] = ""
    notes: Optional[str] = ""

class ContactUpdate(ContactCreate):
    is_active: Optional[bool] = True

@router.get("/contacts")
async def contacts_page(request: Request):
    """通訊錄管理 UI"""
    return templates.TemplateResponse("contacts.html", {
        "request": request,
        "active_page": "contacts"
    })

@router.get("/api/contacts")
async def list_contacts():
    """取得所有聯絡人 (JSON)"""
    db = SessionLocal()
    try:
        contacts = db.query(OrgContact).order_by(OrgContact.org_name).all()
        return {"contacts": [c.to_dict() for c in contacts]}
    finally:
        db.close()

@router.post("/api/contacts")
async def create_contact(data: ContactCreate):
    """新增聯絡人"""
    db = SessionLocal()
    try:
        contact = OrgContact(**data.dict())
        db.add(contact)
        db.commit()
        return {"success": True, "message": "聯絡人已新增"}
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()

@router.put("/api/contacts/{contact_id}")
async def update_contact(contact_id: int, data: ContactUpdate):
    """更新聯絡人"""
    db = SessionLocal()
    try:
        contact = db.query(OrgContact).filter_by(id=contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
            
        for key, value in data.dict().items():
            setattr(contact, key, value)
            
        db.commit()
        return {"success": True, "message": "聯絡人已更新"}
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()

@router.delete("/api/contacts/{contact_id}")
async def delete_contact(contact_id: int):
    """刪除聯絡人"""
    db = SessionLocal()
    try:
        contact = db.query(OrgContact).filter_by(id=contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        db.delete(contact)
        db.commit()
        return {"success": True, "message": "聯絡人已刪除"}
    finally:
        db.close()

@router.get("/api/contacts/{contact_id}/qrcode")
async def get_contact_qrcode(contact_id: int):
    """取得聯絡人 vCard 的 QR Code 圖片"""
    db = SessionLocal()
    try:
        contact = db.query(OrgContact).filter_by(id=contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
            
        img_bytes = generate_vcard_qrcode(contact)
        if not img_bytes:
            raise HTTPException(status_code=500, detail="QR Code generation failed (qrcode package missing?)")
            
        return Response(content=img_bytes, media_type="image/png")
    finally:
        db.close()

@router.get("/api/contacts/{contact_id}/vcard")
async def export_single_vcard(contact_id: int):
    """匯出單一聯絡人 vCard"""
    db = SessionLocal()
    try:
        contact = db.query(OrgContact).filter_by(id=contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
            
        vcard_str = generate_vcard(contact)
        filename = f"{contact.org_name}_{contact.contact_name}.vcf"
        
        return Response(
            content=vcard_str.encode("utf-8"),
            media_type="text/vcard",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    finally:
        db.close()

@router.get("/api/contacts/export-vcard")
async def export_all_vcards():
    """匯出所有聯絡人 vCard"""
    db = SessionLocal()
    try:
        contacts = db.query(OrgContact).filter_by(is_active=True).all()
        vcard_strs = [generate_vcard(c) for c in contacts]
        combined_vcard = "\n".join(vcard_strs)
        
        filename = "all_contacts.vcf"
        return Response(
            content=combined_vcard.encode("utf-8"),
            media_type="text/vcard",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    finally:
        db.close()

@router.get("/api/contacts/export-csv")
async def export_contacts_csv():
    """匯出所有聯絡人 CSV"""
    db = SessionLocal()
    try:
        contacts = db.query(OrgContact).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "機關名稱", "統一編號", "聯絡人姓名", "職稱", "電話", "手機", 
            "Email", "地址", "部門", "標籤", "備註"
        ])
        for c in contacts:
            writer.writerow([
                c.org_name, c.org_tax_id, c.contact_name, c.title, c.phone, c.mobile,
                c.email, c.address, c.department, c.tags, c.notes
            ])
            
        filename = "contacts.csv"
        content = "\ufeff" + output.getvalue()
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        )
    finally:
        db.close()

@router.post("/api/contacts/sync")
async def sync_contacts_from_tenders():
    """從招標與公開徵求案件中同步承辦人資訊到通訊錄"""
    db = SessionLocal()
    try:
        from models import Tender, BiddingTender
        
        # 1. 取得所有案件
        tenders = db.query(Tender).filter(Tender.contact_person != "", Tender.contact_person != None).all()
        biddings = db.query(BiddingTender).filter(BiddingTender.contact_person != "", BiddingTender.contact_person != None).all()
        
        # 2. 查詢現有的聯絡人以防重複
        existing_contacts = db.query(OrgContact).all()
        existing_keys = {(c.org_name, c.contact_name) for c in existing_contacts}
        
        added_count = 0
        
        # 3. 處理公開徵求
        for t in tenders:
            key = (t.org_name, t.contact_person)
            if key not in existing_keys:
                contact = OrgContact(
                    org_name=t.org_name,
                    contact_name=t.contact_person,
                    phone=t.phone,
                    source_tender_id=t.tender_id,
                    tags="公開徵求同步",
                    notes=f"從案號 {t.tender_id} 自動同步"
                )
                db.add(contact)
                existing_keys.add(key)
                added_count += 1
                
        # 4. 處理公開招標
        for b in biddings:
            key = (b.org_name, b.contact_person)
            if key not in existing_keys:
                contact = OrgContact(
                    org_name=b.org_name,
                    contact_name=b.contact_person,
                    phone=b.phone,
                    source_tender_id=b.tender_id,
                    tags="公開招標同步",
                    notes=f"從招標案號 {b.tender_id} 自動同步"
                )
                db.add(contact)
                existing_keys.add(key)
                added_count += 1
                
        if added_count > 0:
            db.commit()
            
        return {
            "success": True,
            "message": f"同步完成，共新增 {added_count} 筆聯絡人資料！",
            "added_count": added_count
        }
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
    finally:
        db.close()
