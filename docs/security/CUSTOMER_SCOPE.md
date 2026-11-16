# Acceso a clientes por sucursal — AgendaVoice AI 4.2.2

## Modelo

- Los clientes pertenecen a la **empresa** (teléfono único por tenant). Una misma persona no se duplica entre sucursales.
- Cada cliente tiene una **sucursal de origen** (`home_branch_id`), donde se registró.
- Un usuario con acceso a sucursales concretas ve un cliente si:
  1. la sucursal de origen del cliente está entre sus sucursales, o
  2. el cliente tiene al menos una reserva en alguna de sus sucursales.
- `TENANT_ADMIN` y `SUPER_ADMIN` ven todos los clientes.

## Efectos en la API

- `GET /customers`: solo devuelve los clientes visibles para el usuario.
- `POST /customers`: el cliente se asocia a `branch_id` si se indica. Un usuario con una sola sucursal no necesita indicarla. Con varias, debe indicarla y debe tener acceso a ella.
- Si el teléfono ya existe en la empresa, responde 409 con un mensaje genérico. Un encargado de otra sucursal no recibe los datos del cliente existente. Un administrador debe revisarlo.
- `POST /appointments`: si el cliente no es visible para el usuario, responde 404 "Sucursal, cliente o servicio no encontrado". No se confirma si el cliente existe.

## Trade-off conocido

Un encargado sí puede saber que un teléfono ya está registrado en la empresa, porque recibe el 409. No recibe datos del cliente. Eliminar esa señal requiere un flujo de asociación por el administrador, que queda pendiente.

## Migración

`0005_r422_customer_home_branch` agrega la columna y rellena `home_branch_id` con la sucursal de la primera reserva de cada cliente. Los clientes sin reservas quedan sin sucursal de origen y solo los ven los administradores hasta que tengan una reserva.

## Implementación

- Regla de referencia y pruebas sin base de datos: `app/modules/customers/visibility.py`.
- Consulta SQL: `_customer_scope` y `_customer_visible` en `app/main.py`. Deben mantenerse alineadas con la regla de referencia.
