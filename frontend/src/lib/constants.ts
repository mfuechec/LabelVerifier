export const CANONICAL_WARNING =
  'GOVERNMENT WARNING: (1) According to the Surgeon General, ' +
  'women should not drink alcoholic beverages during pregnancy ' +
  'because of the risk of birth defects. (2) Consumption of ' +
  'alcoholic beverages impairs your ability to drive a car or ' +
  'operate machinery, and may cause health problems.';

export const STATUS_COLORS: Record<string, string> = {
  match: 'var(--emerald-600)',
  content_mismatch: 'var(--red-600)',
  field_missing: 'var(--red-600)',
  extraction_uncertain: 'var(--yellow-500)',
};

export const STATUS_LABELS: Record<string, string> = {
  match: 'Match',
  content_mismatch: 'Mismatch',
  field_missing: 'Missing',
  extraction_uncertain: 'Uncertain',
  pass: 'Pass',
  needs_review: 'Needs Review',
  fail: 'Fail',
  pending: 'Pending',
};

export const FIELD_LABELS: Record<string, string> = {
  brand_name: 'Brand Name',
  class_type: 'Class/Type',
  alcohol_content: 'Alcohol Content',
  net_contents: 'Net Contents',
  producer_name: 'Producer Name',
  producer_address: 'Producer Address',
  country_of_origin: 'Country of Origin',
  importer_name: 'Importer Name',
  importer_address: 'Importer Address',
  government_warning: 'Government Warning',
  sulfites_declaration: 'Sulfites Declaration',
};

export const BEVERAGE_TYPES = [
  { value: 'distilled_spirits', label: 'Distilled Spirits' },
  { value: 'wine', label: 'Wine' },
  { value: 'beer', label: 'Beer' },
];
