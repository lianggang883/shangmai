from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.member import Member
from app.models.billing import ActionPowerAccount, ActionPowerTransaction, TxType
from app.dependencies.auth import get_current_member
from app.schemas.common import success, fail

router = APIRouter()  # NO prefix - main.py provides /api/v1/billing


async def get_or_create_account(member_id: str, db: AsyncSession) -> ActionPowerAccount:
    q = select(ActionPowerAccount).where(ActionPowerAccount.member_id == member_id)
    result = await db.execute(q)
    account = result.scalar_one_or_none()
    if not account:
        account = ActionPowerAccount(member_id=member_id, monthly_free=50, purchased=0, gifted=0, frozen=0)
        db.add(account)
        await db.flush()
    return account


@router.get("/balance")
async def get_balance(
    current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    account = await get_or_create_account(str(current_member.id), db)
    return success(data={
        "balance": current_member.action_power_balance,
        "monthly_free": account.monthly_free,
        "purchased": account.purchased,
        "gifted": account.gifted,
        "frozen": account.frozen,
    })


@router.post("/recharge")
async def recharge(
    amount: int = 50, pay_method: str = "wechat",
    current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    if amount <= 0:
        return fail(message="充值数量必须大于0")
    account = await get_or_create_account(str(current_member.id), db)
    current_member.action_power_balance += amount
    account.purchased += amount
    new_balance = current_member.action_power_balance
    db.add(ActionPowerTransaction(
        account_id=str(account.id), tx_type=TxType.RECHARGE.value,
        amount=amount, balance_after=new_balance,
        description=f"充值{amount}行动力({pay_method})",
    ))
    await db.commit()
    return success(data={"amount": amount, "balance": new_balance})


@router.get("/transactions")
async def list_transactions(
    limit: int = 20, offset: int = 0,
    current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    account = await get_or_create_account(str(current_member.id), db)
    txs = (await db.execute(
        select(ActionPowerTransaction).where(ActionPowerTransaction.account_id == str(account.id))
        .order_by(ActionPowerTransaction.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    total = (await db.execute(select(func.count(ActionPowerTransaction.id)).where(
        ActionPowerTransaction.account_id == str(account.id)))).scalar()
    return success(data={
        "items": [{
            "id": str(tx.id), "tx_type": tx.tx_type, "amount": tx.amount,
            "balance_after": tx.balance_after, "description": tx.description,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        } for tx in txs], "total": total or 0,
    })


@router.post("/gift")
async def gift_action_power(
    to_member_id: str, amount: int,
    current_member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    if amount <= 0:
        return fail(message="赠送数量必须大于0")
    if current_member.action_power_balance < amount:
        return fail(code=402, message="行动力不足")
    target = (await db.execute(select(Member).where(Member.id == to_member_id))).scalar_one_or_none()
    if not target:
        return fail(message="目标用户不存在")
    current_member.action_power_balance -= amount
    target.action_power_balance += amount
    from_acc = await get_or_create_account(str(current_member.id), db)
    to_acc = await get_or_create_account(to_member_id, db)
    db.add(ActionPowerTransaction(account_id=str(from_acc.id), tx_type=TxType.GIFT.value,
        amount=-amount, balance_after=current_member.action_power_balance,
        description=f"赠送{amount}行动力给{target.name}"))
    db.add(ActionPowerTransaction(account_id=str(to_acc.id), tx_type=TxType.GIFT.value,
        amount=amount, balance_after=target.action_power_balance,
        description=f"收到{current_member.name}赠送的{amount}行动力"))
    await db.commit()
    return success(data={"gifted": amount, "balance": current_member.action_power_balance})
