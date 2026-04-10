'use client'

import React from 'react'
import { TextInput, FieldLabel, useField } from '@payloadcms/ui'
import type { TextFieldClientProps } from 'payload'

type ColorPickerProps = TextFieldClientProps

export const ColorPicker: React.FC<ColorPickerProps> = (props) => {
    const { field, path, readOnly } = props
    const { value, setValue } = useField<string>({ path: path || field.name })

    return (
        <div className="field-type color-picker">
            <FieldLabel
                htmlFor={`field-${path || field.name}`}
                label={field.label}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input
                    type="color"
                    value={value || '#000000'}
                    onChange={(e) => setValue(e.target.value)}
                    disabled={readOnly}
                    style={{
                        width: '60px',
                        height: '40px',
                        border: '1px solid #ccc',
                        borderRadius: '4px',
                        cursor: readOnly ? 'not-allowed' : 'pointer'
                    }}
                />
                <TextInput
                    value={value || ''}
                    onChange={setValue}
                    path={path || field.name}
                    readOnly={readOnly}
                    placeholder="#000000"
                    style={{ flex: 1 }}
                />
            </div>
            {field.admin?.description && (
                <div className="field-description" style={{ marginTop: '8px', fontSize: '0.875rem', color: '#666' }}>
                    {typeof field.admin.description === 'string' ? field.admin.description : JSON.stringify(field.admin.description)}
                </div>
            )}
        </div>
    )
}

export default ColorPicker