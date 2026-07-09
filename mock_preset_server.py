"""
Mock 预设值服务 - 用于本地联调测试

启动方式:
    python mock_preset_server.py

默认监听: http://127.0.0.1:9800
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Signing Preset Service")

# 预设值数据：总部 + 子公司。身份证号均为本地联调用非真实测试值。
PRESETS = {
    "东软集团股份有限公司": {
        "entity_name": "东软集团股份有限公司",
        "legal_rep_name": "刘积仁",
        "legal_rep_id_number": "000000000000000001",
        "authorized_reps": [
            {"name": "李四", "id_number": "000000000000000002"},
            {"name": "王五", "id_number": "000000000000000003"},
        ],
        "bank_name": "招商银行股份有限公司沈阳南湖科技开发区支行",
        "bank_account": "240380425610001",
        "account_holder": "东软集团股份有限公司",
        "address": "沈阳市浑南新区新秀街2号",
        "phone": "024-23783000",
        "fax": "024-23783616",
        "website": "http://www.neusoft.com",
        "postal_code": "110179",
    },
    "东软集团（上海）有限公司": {
        "entity_name": "东软集团（上海）有限公司",
        "legal_rep_name": "张三",
        "legal_rep_id_number": "000000000000000004",
        "authorized_reps": [
            {"name": "吴九", "id_number": "000000000000000005"},
            {"name": "郑十", "id_number": "000000000000000006"},
        ],
        "bank_name": "交通银行上海闵行支行",
        "bank_account": "310066674018170042489",
        "account_holder": "东软集团（上海）有限公司",
        "address": "上海市闵行区紫月路1000号1幢4层",
        "phone": "021-50801234",
        "fax": "021-50801235",
        "website": "http://www.neusoft.com",
        "postal_code": "201203",
    },
}


@app.post("/api/v1/signature-presets/by-entity-name")
async def get_preset(request: Request):
    body = await request.json()
    entity_name = body.get("entity_name", "")

    preset = PRESETS.get(entity_name)
    if preset is None:
        return JSONResponse(status_code=404, content={"error": f"未找到实体: {entity_name}"})

    return {"data": preset}


@app.get("/health")
async def health():
    return {"status": "ok", "entities": list(PRESETS.keys())}


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("Mock 预设值服务已启动")
    print(f"地址: http://127.0.0.1:9800")
    print(f"接口: POST /api/v1/signature-presets/by-entity-name")
    print(f"已配置实体: {list(PRESETS.keys())}")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=9800)
