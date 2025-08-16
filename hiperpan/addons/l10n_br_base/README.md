# Hiperpan - Brazilian Base Module

## Phone Field Auto-population Feature

This module includes a custom phone field widget that automatically prepopulates the phone field with "34" when:

1. The phone field is empty
2. The country is set to Brazil (BR)
3. The user focuses on the phone field

### Implementation Details

- **Custom Widget**: `l10n_br_phone` extends the standard Odoo phone widget
- **JavaScript File**: `static/src/js/phone_field.js`
- **Assets**: Included via `static/src/assets.xml`
- **Applied to**: Both `phone` and `mobile` fields in partner forms

### How It Works

When a user focuses on an empty phone field in a partner form:
1. The widget checks if the field is empty
2. It verifies the country is set to Brazil
3. If both conditions are met, it automatically inserts "34" as the DDD (area code)
4. The user can then continue typing the rest of the phone number

### Files Modified

- `views/res_partner_views.xml` - Updated phone and mobile fields to use custom widget
- `static/src/js/phone_field.js` - Custom widget implementation
- `static/src/assets.xml` - Asset inclusion
- `__manifest__.py` - Added assets.xml to data files

### Usage

The feature works automatically - no additional configuration is required. Simply focus on an empty phone field when the country is Brazil, and it will be prepopulated with "34".
