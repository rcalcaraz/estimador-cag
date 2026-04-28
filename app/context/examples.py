"""Ejemplos few-shot de estimaciones históricas para inyectar en el prompt (CAG / RAG de contexto)."""

ESTIMATION_EXAMPLES = [
    {
        "meeting_summary": (
            "El cliente, una pyme de logística, necesita una plataforma web para gestionar "
            "almacenes, entradas/salidas de stock, alertas de mínimos y un panel para el "
            "responsable de compras. Integración futura con su ERP actual vía CSV (fase 2), "
            "pero en esta fase solo web responsive y roles internos (admin, operario, solo lectura)."
        ),
        "estimation": """
## Estimación: Plataforma web de gestión de inventario

### Desglose de tareas
1. Discovery, wireframes y diseño UI/UX responsive: 40 h · 3.200 €
2. Backend API REST (CRUD artículos, movimientos, ubicaciones): 60 h · 4.800 €
3. Autenticación, roles y auditoría básica de cambios: 22 h · 1.760 €
4. Dashboard con KPIs (rotación, valor stock, alertas): 32 h · 2.560 €
5. Importación/exportación CSV y jobs programados: 18 h · 1.440 €
6. Testing automatizado (API + E2E críticos) y QA manual: 28 h · 2.240 €
7. Despliegue, CI/CD y documentación técnica: 15 h · 1.200 €

**Total estimado: 215 h · ~17.200 €** (tarifa media orientativa 80 €/h)
**Equipo recomendado:** 2 desarrolladores full-stack + 1 diseñador UX a media jornada
**Duración estimada:** 7–9 semanas calendario (1 sprint de diseño + 3–4 de implementación)
**Riesgos / supuestos:** sin integración ERP en tiempo real en esta fase; datos maestros provistos por el cliente en semana 2.
""".strip(),
    },
    {
        "meeting_summary": (
            "Una fintech quiere un portal para clientes corporativos donde consulten extractos, "
            "descarguen facturas en PDF y abran incidencias de facturación. Debe cumplir accesibilidad "
            "AA, SSO con Azure AD del cliente y trazas de auditoría. El núcleo de pagos ya existe; "
            "este proyecto es solo capa B2B y reporting ligero."
        ),
        "estimation": """
## Estimación: Portal B2B de facturación e incidencias

### Desglose de tareas
1. Análisis de requisitos, flujos y diseño UI (WCAG AA): 36 h · 3.240 €
2. Front SPA (listados, filtros, detalle factura, descarga PDF): 52 h · 4.680 €
3. Integración SSO (OIDC / Azure AD) y gestión de sesiones: 24 h · 2.160 €
4. BFF/API gateway sobre servicios de facturación existentes: 44 h · 3.960 €
5. Módulo de tickets (creación, estados, comentarios, notificaciones email): 38 h · 3.420 €
6. Informes exportables (CSV/Excel) y límites de descarga: 20 h · 1.800 €
7. Seguridad (throttling, logs de auditoría), pentest remediación menor: 26 h · 2.340 €
8. QA regresión, accesibilidad y UAT con cliente: 30 h · 2.700 €

**Total estimado: 270 h · ~24.300 €** (tarifa media orientativa 90 €/h perfil senior)
**Equipo recomendado:** 1 tech lead / backend, 1 frontend, 0,5 QA; apoyo puntual DevOps
**Duración estimada:** 10–12 semanas (dependencia de entorno Azure AD y de APIs legacy)
**Riesgos / supuestos:** contratos de API de facturación estables; PDFs generados server-side ya disponibles o acordado alcance de generación nueva.
""".strip(),
    },
]
