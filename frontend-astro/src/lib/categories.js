// Slugs map to labels whose lowercase form contains one of the Supervisor's
// _CATEGORY_KEYWORDS (backend/agents/supervisor.py) so the seed message on
// entering a category chat reliably sets selected_category server-side.
export const CATEGORIES = [
  { slug: 'laptops', label: 'Laptops' },
  { slug: 'mobiles', label: 'Mobiles' },
  { slug: 'tvs', label: 'TVs' },
  { slug: 'refrigerators', label: 'Refrigerators' },
  { slug: 'smart-watches', label: 'Smart Watches' },
  { slug: 'washing-machines', label: 'Washing Machines' },
];

export function categoryFromSlug(slug) {
  return CATEGORIES.find((c) => c.slug === slug) || null;
}
