# GEØ.IA Carbon

Motor de inventário, estoque e remoção de carbono para florestas, restauração e
sistemas agroflorestais, com camada geoespacial sobre o Google Earth Engine.

    pip install fastapi pydantic pytest httpx uvicorn
    python -m pytest carbon/tests -q          # 233 testes
    python -m scripts.audit_carbon_science    # auditoria científica da base
    python -m examples.example_saf            # exemplo funcional
    uvicorn carbon.app:app --reload           # API standalone (dev)

Camada geoespacial (opcional — o motor roda sem ela):

    pip install -r requirements-gee.txt
    earthengine authenticate
    $env:GEE_ENABLED = "true"
    python -m scripts.test_gee_carbon
    python -m examples.gee_coordinate_analysis --lat -24.497 --lon -47.844 --area-ha 100 --year 2024

Integração no backend existente:

    from carbon.api.routes import router as carbon_router
    app.include_router(carbon_router)

## Princípio

Ausência declarada vale mais que número inventado. Pool sem medição é `null`,
nunca zero. Incerteza sem componente calculável é `not_available`, nunca ±10%.
Índice espectral não é carbono — e isso é verificado estaticamente sobre a
árvore sintática de todo o pacote, não só nos caminhos testados.

## Documentos

- `CARBON_ENGINE.md` — arquitetura, fórmulas, unidades, fatores, integração GEE
- `CARBON_DELIVERY.md` — entrega, testes, limitações, pendências de validação
- `CARBON_SCIENTIFIC_VALIDATION.md` — estado de validação fator a fator (gerado)
- `CARBON_REFERENCES.md` — bibliografia e datasets, com nível de acesso (gerado)
