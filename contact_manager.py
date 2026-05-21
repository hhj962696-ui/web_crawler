"""
企業通訊錄管理模組 (階段 3)
處理 vCard 產生、QR Code 產生、以及從爬蟲資料同步聯絡人
"""

import io
import logging
from typing import Optional

try:
    import qrcode
except ImportError:
    qrcode = None

from models import SessionLocal, OrgContact, Tender, BiddingTender

logger = logging.getLogger(__name__)


def generate_vcard(contact: OrgContact) -> str:
    """產生 vCard 格式字串 (v3.0)，iPhone 可直接匯入"""
    vcard = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{contact.contact_name};;;;",
        f"FN:{contact.contact_name}",
    ]

    if contact.org_name:
        vcard.append(f"ORG:{contact.org_name}")
    if contact.title:
        vcard.append(f"TITLE:{contact.title}")
    
    # 手機優先，其次是辦公室電話
    if contact.mobile:
        vcard.append(f"TEL;TYPE=CELL,VOICE:{contact.mobile}")
    if contact.phone:
        vcard.append(f"TEL;TYPE=WORK,VOICE:{contact.phone}")
        
    if contact.email:
        vcard.append(f"EMAIL;TYPE=WORK:{contact.email}")
        
    if contact.address:
        # ADR 格式: Post Office Box; Extended Address; Street; Locality; Region; Postal Code; Country
        # 這裡簡單塞在 Street 欄位
        vcard.append(f"ADR;TYPE=WORK:;;{contact.address};;;;")
        
    notes = []
    if contact.department:
        notes.append(f"部門: {contact.department}")
    if contact.source_tender_id:
        notes.append(f"來源案號: {contact.source_tender_id}")
    if contact.notes:
        notes.append(contact.notes)
        
    if notes:
        vcard.append(f"NOTE:{' | '.join(notes)}")

    vcard.append("END:VCARD")
    return "\n".join(vcard)


def generate_vcard_qrcode(contact: OrgContact) -> Optional[bytes]:
    """產生包含 vCard 資訊的 QR Code 圖片 (PNG bytes)"""
    if not qrcode:
        logger.error("未安裝 qrcode 套件，無法產生 QR Code")
        return None
        
    vcard_str = generate_vcard(contact)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(vcard_str.encode("utf-8"))
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def sync_contacts_from_tenders(tender_id: str, source_table: str):
    """
    從剛爬到的標案中，萃取聯絡人資訊並同步至 org_contacts 表。
    若該聯絡人已存在（相同機關+相同姓名），則跳過。
    """
    db = SessionLocal()
    try:
        tender = None
        if source_table == "tenders":
            tender = db.query(Tender).filter_by(tender_id=tender_id).first()
        elif source_table == "bidding_tenders":
            tender = db.query(BiddingTender).filter_by(tender_id=tender_id).first()
            
        if not tender:
            return
            
        org_name = tender.org_name
        contact_name = tender.contact_person
        phone = tender.phone
        
        # 必須有機關和聯絡人才有意義
        if not org_name or not contact_name:
            return
            
        # 處理 "不明"、"無"、"空白" 等無效聯絡人
        invalid_names = {"不明", "無", "空白", "-", "未提供", "同上"}
        if contact_name.strip() in invalid_names:
            return
            
        # 檢查是否已存在
        existing = db.query(OrgContact).filter(
            OrgContact.org_name == org_name,
            OrgContact.contact_name == contact_name
        ).first()
        
        if existing:
            # 已經存在，可以視情況決定要不要更新電話，這裡先不蓋掉人工編輯過的資料
            return
            
        new_contact = OrgContact(
            org_name=org_name,
            contact_name=contact_name,
            phone=phone,
            source_tender_id=tender_id,
            tags="自動匯入"
        )
        db.add(new_contact)
        db.commit()
        logger.info(f"成功同步聯絡人至通訊錄: {org_name} - {contact_name}")
        
    except Exception as e:
        logger.error(f"同步聯絡人失敗 ({tender_id}): {e}", exc_info=True)
    finally:
        db.close()
