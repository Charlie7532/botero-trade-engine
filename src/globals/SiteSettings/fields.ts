import type { Field } from 'payload'

const contact: Field = {
    name: 'contact',
    type: 'group',
    label: 'Contact Information',
    fields: [
        {
            name: 'email',
            type: 'email',
            label: 'Contact Email',
        },
        {
            name: 'phone',
            type: 'text',
            label: 'Phone Number',
        },
        {
            name: 'address',
            type: 'textarea',
            label: 'Address',
        },
    ],
}

const branding: Field = {
    name: 'branding',
    type: 'group',
    label: 'Branding & Logo',
    fields: [
        {
            name: 'siteName',
            type: 'text',
            label: 'Site Name',
            admin: {
                description: 'Used as fallback when logo is not available',
            },
        },
        {
            name: 'logoMode',
            type: 'select',
            label: 'Logo Configuration',
            required: true,
            defaultValue: 'simple',
            options: [
                {
                    label: 'Simple (One logo for all themes)',
                    value: 'simple',
                },
                {
                    label: 'Light/Dark (Different logos for light and dark themes)',
                    value: 'lightDark',
                },
            ],
            admin: {
                description: 'Choose how you want to configure your logos',
            },
        },
        {
            name: 'logo',
            type: 'upload',
            relationTo: 'media',
            label: 'Logo',
            admin: {
                condition: (_, siblingData) => siblingData.logoMode === 'simple',
            },
        },
        {
            type: 'row',
            fields: [
                {
                    name: 'logoLight',
                    type: 'upload',
                    relationTo: 'media',
                    label: 'Light Mode Logo',
                    admin: {
                        condition: (_, siblingData) => siblingData.logoMode === 'lightDark',
                        width: '50%'
                    },
                },
                {
                    name: 'logoDark',
                    type: 'upload',
                    relationTo: 'media',
                    label: 'Dark Mode Logo',
                    admin: {
                        condition: (_, siblingData) => siblingData.logoMode === 'lightDark',
                        width: '50%'
                    },
                },
            ]
        },
        {
            name: 'favicon',
            type: 'upload',
            relationTo: 'media',
            label: 'Favicon',
            admin: {
                description: 'Upload your favicon (the small icon displayed in browser tabs). Recommended: 32x32px PNG or ICO file.',
            },
        },
        {
            name: 'adminLogo',
            type: 'upload',
            relationTo: 'media',
            label: 'Admin Logo',
            admin: {
                description: 'Upload a logo specifically for the admin panel.',
            },
        },
    ],
}

const themeSettings: Field = {
    name: 'themeSettings',
    type: 'group',
    label: 'Theme and Appearance',
    fields: [
        {
            name: 'themeMode',
            type: 'select',
            label: 'Theme Mode',
            required: true,
            defaultValue: 'both',
            options: [
                {
                    label: 'Light Theme Only',
                    value: 'light-only',
                },
                {
                    label: 'Dark Theme Only',
                    value: 'dark-only',
                },
                {
                    label: 'Both (User can switch)',
                    value: 'both',
                },
            ],
            admin: {
                description: 'Choose whether your site supports light theme, dark theme, or both',
            },
        },
        {
            name: 'defaultTheme',
            type: 'select',
            label: 'Default Theme',
            required: true,
            defaultValue: 'light',
            options: [
                {
                    label: 'Light',
                    value: 'light',
                },
                {
                    label: 'Dark',
                    value: 'dark',
                },
                {
                    label: 'System Preference',
                    value: 'system',
                },
            ],
            admin: {
                description: 'Choose the default theme when users first visit your site',
                condition: (_, siblingData) => siblingData.themeMode === 'both',
            },
        },
        {
            name: 'customColors',
            type: 'checkbox',
            label: 'Enable Custom Colors',
            defaultValue: false,
            admin: {
                description: 'Enable this to customize primary and secondary colors for your site',
            },
        },
        {
            name: 'primaryColor',
            type: 'text',
            label: 'Primary Color',
            defaultValue: '#015A86',
            admin: {
                condition: (_, siblingData) => siblingData.customColors === true,
                description: 'Choose your primary brand color. This will be automatically adjusted for light and dark themes.',
                components: {
                    Field: {
                        path: '@/components/fields/ColorPicker',
                    },
                },
            },
        },
        {
            name: 'secondaryColor',
            type: 'text',
            label: 'Secondary Color',
            defaultValue: '#6B7280',
            admin: {
                condition: (_, siblingData) => siblingData.customColors === true,
                description: 'Choose your secondary color. This will be automatically adjusted for light and dark themes.',
                components: {
                    Field: {
                        path: '@/components/fields/ColorPicker',
                    },
                },
            },
        },
        {
            name: 'customFonts',
            type: 'checkbox',
            label: 'Enable Custom Fonts',
            defaultValue: false,
            admin: {
                description: 'Enable this to customize fonts for headings and body text',
            },
        },
        {
            name: 'typography',
            type: 'group',
            label: 'Typography',
            admin: {
                condition: (_, siblingData) => siblingData.customFonts === true,
            },
            fields: [],
        },
    ],
}

const socialMedia: Field = {
    name: 'socialMedia',
    type: 'group',
    label: 'Social Media',
    fields: [
        {
            name: 'platforms',
            type: 'array',
            label: 'Platforms',
            minRows: 0,
            maxRows: 10,
            fields: [
                {
                    type: 'row',
                    fields: [
                        {
                            name: 'platform',
                            type: 'select',
                            label: 'Platform',
                            required: true,
                            options: [
                                { label: 'Facebook', value: 'facebook' },
                                { label: 'Twitter/X', value: 'twitter' },
                                { label: 'Instagram', value: 'instagram' },
                                { label: 'LinkedIn', value: 'linkedin' },
                                { label: 'YouTube', value: 'youtube' },
                                { label: 'TikTok', value: 'tiktok' },
                                { label: 'GitHub', value: 'github' },
                                { label: 'Discord', value: 'discord' },
                            ],
                            admin: {
                                width: '30%',
                            },
                        },
                        {
                            name: 'url',
                            type: 'text',
                            label: 'URL',
                            required: true,
                            admin: {
                                width: '70%',
                                placeholder: 'https://example.com',
                            },
                        },
                    ],
                },
            ],
            admin: {
                initCollapsed: true,
                components: {
                    RowLabel: '@/globals/SiteSettings/RowLabel#RowLabel',
                },
            },
        },
    ],
}

const seo: Field = {
    name: 'seo',
    type: 'group',
    label: 'Global SEO Settings',
    fields: [
        {
            name: 'siteDescription',
            type: 'textarea',
            label: 'Site Description',
            admin: {
                description: 'Default meta description for pages that don\'t have one set',
            },
        },
        {
            name: 'keywords',
            type: 'text',
            label: 'Default Keywords',
            admin: {
                description: 'Comma-separated keywords for SEO',
            },
        },
    ],
}

const legalPolicies: Field = {
    name: 'legalPolicies',
    type: 'array',
    label: 'Legal Policies',
    minRows: 0,
    maxRows: 6,
    fields: [
        {
            type: 'row',
            fields: [
                {
                    name: 'name',
                    type: 'text',
                    required: true,
                    label: 'Name',
                    admin: {
                        placeholder: 'Terms and Conditions',
                        width: '50%'
                    }
                },
                {
                    name: 'label',
                    type: 'text',
                    required: false,
                    label: 'Label (short)',
                    admin: {
                        placeholder: 'Terms',
                        width: '50%'
                    }
                }
            ]
        },
        {
            name: 'type',
            type: 'radio',
            required: true,
            defaultValue: 'reference',
            options: [
                { label: 'Internal link', value: 'reference' },
                { label: 'Custom URL', value: 'custom' },
            ],
            admin: {
                layout: 'horizontal',
                width: '50%'
            }
        },
        {
            name: 'reference',
            type: 'relationship',
            relationTo: ['pages', 'posts'],
            admin: {
                condition: (_, siblingData) => siblingData?.type === 'reference',
                width: '50%'
            }
        },
        {
            name: 'url',
            type: 'text',
            admin: {
                condition: (_, siblingData) => siblingData?.type === 'custom',
                width: '50%'
            }
        },
        {
            name: 'newTab',
            type: 'checkbox',
            label: 'Open in new tab',
            admin: {
                width: '50%'
            }
        }
    ],
    admin: {
        initCollapsed: true,
        components: {
            RowLabel: '@/globals/SiteSettings/PolicyRowLabel#PolicyRowLabel',
        },
        description: 'Add up to 6 legal/legislative policy links (e.g., Privacy, Terms, Cookies). These will be rendered in the footer and mobile menu. If there are more than 2, footer will show first 2 and an Other policies link.'
    }
}

export const siteSettingsFields: Field[] = [
    {
        type: 'tabs',
        tabs: [
            {
                label: 'General',
                fields: [
                    contact,
                    legalPolicies,
                ],
            },
            {
                label: 'Branding & Social Media',
                fields: [
                    branding,
                    themeSettings,
                    socialMedia,
                ],
            },
            {
                label: 'Integrations',
                fields: [],
            },
            {
                label: 'Advance Settings',
                fields: [
                    seo,
                ],
            },
        ],
    },
]
