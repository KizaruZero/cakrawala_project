# Analisa & Konversi: `employee_purchase_requisition` dari Odoo 18 → Odoo 19

## 📋 Ringkasan Modul

Modul `employee_purchase_requisition` adalah modul manajemen permintaan pengadaan barang oleh karyawan dengan alur multi-level approval:
- **Karyawan** membuat requisition
- **Department Head** menyetujui/menolak
- **Requisition Manager** memberikan persetujuan final
- Sistem otomatis membuat **Purchase Order** atau **Internal Transfer**

---

## 🔍 Temuan Kode Odoo 18 (Kondisi Awal)

Meskipun manifest menyebut versi `19.0.1.0.0`, beberapa pola kode di dalamnya masih menggunakan gaya lama (Odoo 16/17/18) yang perlu disesuaikan sepenuhnya untuk Odoo 19:

| Area | Masalah yang Ditemukan |
|------|------------------------|
| **Kanban View** | Menggunakan `t-name="kanban-box"` (gaya lama) |
| **Stock Picking** | Menggunakan `move_ids_without_package` (deprecated di Odoo 19) |
| **Product Description** | Menggunakan `get_product_multiline_description_sale()` dari module sale |
| **Security Groups** | Struktur XML sudah v19 (`privilege_id`) — **benar** |
| **List View** | Masih menggunakan `<list>` — sudah kompatibel v19 |
| **`view_mode`** | Menggunakan `list,form,kanban` — `tree` sudah diganti `list` sejak v17 |
| **Compute count** | Tidak menggunakan `@api.depends_context` — OK untuk use case ini |
| **`_inherit` syntax** | Menggunakan tuple string, bukan list — OK |
| **Report template** | Menggunakan `t-esc` (deprecated di Odoo 17+, diganti `t-out`) |
| **`action_print_report`** | Menggunakan `.read()` return dict, bukan recordset langsung |

---

## 📋 Perbandingan Detail: Odoo 18 vs Odoo 19

### 1. Kanban View Template Name

| | Odoo 17/18 | Odoo 19 |
|---|---|---|
| Template name | `t-name="kanban-box"` | `t-name="card"` |
| Wrapper div | `<div class="oe_kanban_global_click">` | Langsung di dalam `<t t-name="card">` |
| Struktur | Verbose dengan `oe_kanban_content > oe_kanban_card` | Lebih ringkas |

**Sebelum (v18):**
```xml
<kanban>
    <templates>
        <t t-name="kanban-box">
            <div class="oe_kanban_global_click">
                <div class="oe_kanban_content">
                    <div class="oe_kanban_card">
                        <field name="name"/>
                    </div>
                </div>
            </div>
        </t>
    </templates>
</kanban>
```

**Sesudah (v19):**
```xml
<kanban>
    <templates>
        <t t-name="card">
            <field name="name"/>
            <field name="employee_id"/>
        </t>
    </templates>
</kanban>
```

---

### 2. Stock Move Field

| | Odoo 16/17/18 | Odoo 19 |
|---|---|---|
| Field | `move_ids_without_package` | `move_ids` |
| Deskripsi | Field computed yang memfilter move tanpa package | Langsung gunakan `move_ids` |

**Sebelum (v18):**
```python
'move_ids_without_package': [(0, 0, {
    'name': rec.product_id.name,
    ...
})]
```

**Sesudah (v19):**
```python
'move_ids': [(0, 0, {
    'name': rec.product_id.name,
    ...
})]
```

---

### 3. QWeb: `t-esc` → `t-out`

| | Odoo ≤ 17 | Odoo 18/19 |
|---|---|---|
| Directive output | `t-esc` (escape HTML) | `t-out` (preferred, handles markup) |
| Backward compat | `t-esc` masih berfungsi tapi deprecated | `t-out` adalah standar baru |

**Sebelum:**
```xml
<t t-esc="rec['name']"/>
```

**Sesudah:**
```xml
<t t-out="rec['name']"/>
```

---

### 4. Security Groups: Struktur 3-Tier (Sudah v19)

Modul ini **sudah benar** menggunakan struktur 3-tier Odoo 19:

```
ir.module.category → res.groups.privilege → res.groups
```

Ini adalah fitur **baru di Odoo 19** yang menggantikan pola lama `category_id` langsung di `res.groups`.

---

### 5. `get_product_multiline_description_sale()` — Dependency `sale`

Metode ini berasal dari modul `sale`, padahal modul ini tidak bergantung pada `sale`. Ini berpotensi error jika modul `sale` tidak terpasang.

**Solusi v19:** Gunakan `product_id.description_sale or product_id.name` sebagai fallback yang aman.

---

### 6. `_compute_purchase_count` / `_compute_internal_transfer_count` — Missing `@api.depends`

Kedua compute field ini tidak memiliki `@api.depends`, yang menyebabkan:
- Nilai tidak di-recompute saat data berubah
- Odoo 19 akan menampilkan warning di log

**Solusi:** Tambahkan `@api.depends` atau gunakan flag `compute_sudo=True`.

---

### 7. Report Template: Pendekatan Modern

Odoo 19 merekomendasikan penggunaan `t-out` dan akses langsung ke record (bukan via `.read()` dict). Namun karena modul ini menggunakan custom data dict di `action_print_report`, solusi terbaik adalah tetap mempertahankan pola tersebut tapi update `t-esc` → `t-out`.

---

## ✅ Perubahan yang Dilakukan

### File yang Diubah:

| File | Perubahan |
|------|-----------|
| `models/employee_purchase_requisition.py` | Ganti `move_ids_without_package` → `move_ids`; tambah `@api.depends` pada compute fields; fix `_compute_name` dependency |
| `models/requisition_order.py` | Perbaiki `_compute_name`: gunakan fallback tanpa bergantung `sale` module |
| `views/employee_purchase_requisition_views.xml` | Update kanban template `kanban-box` → `card`; update `t-esc` → `t-out` di konten |
| `report/employee_purchase_requisition_templates.xml` | Ganti semua `t-esc` → `t-out` |

### File yang Tidak Perlu Diubah:
- `security/employee_purchase_requisition_groups.xml` — Sudah v19 ✅
- `security/employee_purchase_requisition_security.xml` — OK ✅
- `security/ir.model.access.csv` — OK ✅
- `data/ir_sequence_data.xml` — OK ✅
- `models/hr_employee.py`, `hr_department.py`, `purchase_order.py`, `stock_picking.py` — OK ✅
- `views/requisition_order_views.xml`, `hr_*_views.xml`, dll — OK ✅
- `__manifest__.py` — Versi sudah `19.0.1.0.0` ✅

---

## 🔧 Diff Summary Perubahan

### `models/employee_purchase_requisition.py`
```diff
- # Compute fields tanpa @api.depends (tidak reaktif)
- def _compute_internal_transfer_count(self):
-     self.internal_transfer_count = ...
- def _compute_purchase_count(self):
-     self.purchase_count = ...
+ @api.depends('name')
+ def _compute_internal_transfer_count(self):
+     for rec in self:
+         rec.internal_transfer_count = ...
+ @api.depends('name')
+ def _compute_purchase_count(self):
+     for rec in self:
+         rec.purchase_count = ...

# Dalam action_create_purchase_order:
- 'move_ids_without_package': [(0, 0, {...})]
+ 'move_ids': [(0, 0, {...})]
```

### `models/requisition_order.py`
```diff
- # Bergantung pada modul 'sale' yang tidak di-declare di depends
- option.description = product_lang.get_product_multiline_description_sale()
+ # Aman tanpa modul sale
+ option.description = (product_lang.description_sale
+                       or product_lang.name or '')

# Juga perbaikan bug: self.requisition_product_id → option.requisition_product_id
- lang=self.requisition_product_id.employee_id.lang
+ lang=option.requisition_product_id.employee_id.lang
```

### `views/employee_purchase_requisition_views.xml`
```diff
# Kanban View Template
- <t t-name="kanban-box">
-     <div class="oe_kanban_global_click">
-         <div class="oe_kanban_content">
-             <div class="oe_kanban_card"> ... </div>
-         </div>
-     </div>
- </t>
+ <t t-name="card" class="oe_kanban_global_click">
+     <div class="o_kanban_record_top"> ... </div>
+     <div class="o_kanban_record_body"> ... </div>
+     <div class="o_kanban_record_bottom"> ... </div>
+ </t>
```

### `report/employee_purchase_requisition_templates.xml`
```diff
# Seluruh file: 23 instance
- <t t-esc="rec['...']"/>
+ <t t-out="rec['...']"/>
```

---

## ⚠️ Catatan Tambahan

> **Linting Warning:** `Import "odoo" could not be resolved` dari basedpyright/Pylance adalah perilaku normal jika IDE tidak dikonfigurasi dengan path venv Odoo. Ini **bukan error runtime**. Tambahkan `pyrightconfig.json` di root project untuk menghilangkannya.

> **Catatan `sale` module:** Jika di masa depan modul ini akan diintegrasikan dengan `sale`, tambahkan `'sale'` ke `depends` di `__manifest__.py` dan kembalikan penggunaan `get_product_multiline_description_sale()`.

