# How to Add New Blocks - Complete Guide

This guide explains the block system and how to add new blocks to your Payload CMS site.

## What Are Blocks?

Blocks are reusable content components that editors can add to pages through the Payload admin panel. Think of them as building blocks for your pages.

## Block Architecture

Every block consists of 3 main parts:

```
src/blocks/YourBlock/
├── config.ts       # Defines fields for the admin panel
├── Component.tsx   # Renders the block on the frontend
└── (optional) Component.client.tsx  # For client-side interactivity
```

## The 4-Step Process to Add a Block

### Step 1: Create the Block Config (`config.ts`)

This defines what fields appear in the Payload admin panel.

```typescript
import type { Block } from 'payload'

export const YourBlock: Block = {
  slug: 'yourBlock',              // Unique identifier (camelCase)
  interfaceName: 'YourBlockBlock', // TypeScript type name
  fields: [
    {
      name: 'fieldName',
      type: 'text',
      required: true,
    },
    // Add more fields as needed
  ],
}
```

**Common Field Types:**
- `text` - Single line text
- `textarea` - Multi-line text
- `richText` - Rich text editor
- `select` - Dropdown menu
- `number` - Numeric input
- `checkbox` - Boolean
- `upload` - Media upload (images, files)
- `relationship` - Link to other content

### Step 2: Create the Component (`Component.tsx`)

This renders your block on the frontend.

```typescript
import type { YourBlockBlock as YourBlockBlockProps } from 'src/payload-types'
import React from 'react'

type Props = {
  className?: string
} & YourBlockBlockProps

export const YourBlockBlock: React.FC<Props> = ({ 
  fieldName,  // These come from config.ts
  className 
}) => {
  return (
    <div className={className}>
      <h2>{fieldName}</h2>
    </div>
  )
}
```

**Naming Convention:** Export as `YourBlockBlock` (BlockName + "Block")

### Step 3: Register in Pages Collection

Add your block to `src/collections/Pages/index.ts`:

```typescript
// 1. Import the config
import { YourBlock } from '../../blocks/YourBlock/config'

// 2. Add to the blocks array (around line 75)
{
  name: 'layout',
  type: 'blocks',
  blocks: [
    CallToAction, 
    Content, 
    MediaBlock, 
    Archive, 
    FormBlock, 
    SignupCTABlock, 
    TwoColumnTextImageBlock,
    YourBlock,  // <-- Add here
  ],
}
```

### Step 4: Register in RenderBlocks

Add your component to `src/blocks/RenderBlocks.tsx`:

```typescript
// 1. Import the component
import { YourBlockBlock } from '@/blocks/YourBlock/Component'

// 2. Add to blockComponents object
const blockComponents = {
  archive: ArchiveBlock,
  content: ContentBlock,
  cta: CallToActionBlock,
  formBlock: FormBlock,
  mediaBlock: MediaBlock,
  signupCTA: SignupCTA,
  twoColumnTextImage: TwoColumnTextImage,
  yourBlock: YourBlockBlock,  // <-- slug: Component
}
```

**Important:** The key must match the `slug` from config.ts!

## Example: SimpleCard Block

See `src/blocks/SimpleCard/` for a complete working example with:
- Text input (title)
- Textarea (description)
- Select dropdown (backgroundColor)
- Conditional styling based on selection

## Advanced Features

### Client-Side Interactivity

If your block needs JavaScript interactivity (buttons, forms, animations):

1. Create `Component.client.tsx` with `'use client'` directive
2. Import it in `Component.tsx` (which stays server-side)

Example structure:
```typescript
// Component.tsx (Server Component)
import { YourBlockClient } from './Component.client'

export const YourBlockBlock = (props) => {
  return <YourBlockClient {...props} />
}

// Component.client.tsx (Client Component)
'use client'
export const YourBlockClient = (props) => {
  const [state, setState] = useState()
  // Interactive logic here
}
```

### Rich Text Fields

For rich text content:

```typescript
// In config.ts
import { lexicalEditor } from '@payloadcms/richtext-lexical'

{
  name: 'content',
  type: 'richText',
  editor: lexicalEditor(),
}

// In Component.tsx
import RichText from '@/components/RichText'

<RichText data={content} />
```

### Media/Image Fields

```typescript
// In config.ts
{
  name: 'image',
  type: 'upload',
  relationTo: 'media',
}

// In Component.tsx
import { Media } from '@/components/Media'

<Media resource={image} />
```

## Testing Your Block

1. **Generate Types:** Run `npm run generate:types` to update TypeScript types
2. **Restart Dev Server:** Restart your Next.js dev server
3. **Test in Admin:** Go to Payload admin → Pages → Edit a page → Add your block
4. **View Frontend:** Save and view the page to see your block rendered

## Common Patterns

### Conditional Styling
```typescript
className={cn('base-classes', {
  'style-a': condition === 'a',
  'style-b': condition === 'b',
})}
```

### Optional Fields
```typescript
{condition && <div>{content}</div>}
```

### Loops
```typescript
{items?.map((item, index) => (
  <div key={index}>{item.name}</div>
))}
```

## Troubleshooting

**Block doesn't appear in admin:**
- Check it's imported and added to Pages collection
- Restart dev server

**TypeScript errors:**
- Run `npm run generate:types`
- Check interfaceName matches usage

**Block doesn't render:**
- Check slug matches in RenderBlocks.tsx
- Check component is imported correctly

**Styling issues:**
- Use Tailwind classes
- Check dark mode variants with `dark:` prefix
- Use `cn()` utility for conditional classes

## File Checklist

When adding a new block, you'll touch these files:

- [ ] Create `src/blocks/YourBlock/config.ts`
- [ ] Create `src/blocks/YourBlock/Component.tsx`
- [ ] Update `src/collections/Pages/index.ts` (import + add to blocks array)
- [ ] Update `src/blocks/RenderBlocks.tsx` (import + add to blockComponents)
- [ ] Run `npm run generate:types`
- [ ] Restart dev server

That's it! You now understand the complete block system.
