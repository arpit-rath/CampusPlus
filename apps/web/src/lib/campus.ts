/**
 * The campus itself: the buildings students can report against, and where
 * each one sits on the schematic map the dashboard heatmap draws.
 *
 * One shared list matters more than it sounds. Similarity search is scoped
 * to "same building", so a report filed against "Block A" can never merge
 * with one filed against "Hostel Block A" — free-text building entry would
 * quietly break clustering. Keeping the report form, the heatmap and
 * `scripts/seed_demo.py` on the same vocabulary is what makes a live
 * submission merge with the seeded history during a demo.
 *
 * Coordinates are a hand-drawn schematic (percentages of the map area), not
 * real geography. That is the honest option here: inventing plausible-looking
 * latitudes and longitudes for a fictional campus would look more impressive
 * and mean less.
 */

export interface CampusBuilding {
  name: string;
  /** Percent from the left of the map area. */
  x: number;
  /** Percent from the top of the map area. */
  y: number;
  zone: "academic" | "residential" | "shared";
}

export const CAMPUS_BUILDINGS: CampusBuilding[] = [
  { name: "Innovation Hall", x: 18, y: 22, zone: "academic" },
  { name: "Academic Block A", x: 41, y: 16, zone: "academic" },
  { name: "Academic Block B", x: 63, y: 18, zone: "academic" },
  { name: "Science Block", x: 84, y: 27, zone: "academic" },
  { name: "Computer Center", x: 26, y: 44, zone: "academic" },
  { name: "Main Library", x: 50, y: 43, zone: "shared" },
  { name: "Cafeteria", x: 76, y: 51, zone: "shared" },
  { name: "Sports Complex", x: 16, y: 65, zone: "shared" },
  { name: "Hostel Block A", x: 40, y: 70, zone: "residential" },
  { name: "Hostel Block B", x: 60, y: 78, zone: "residential" },
  { name: "Hostel Block C", x: 80, y: 70, zone: "residential" },
  { name: "Main Gate", x: 50, y: 92, zone: "shared" },
];

export const BUILDING_NAMES = CAMPUS_BUILDINGS.map((b) => b.name);

const BY_NAME = new Map(CAMPUS_BUILDINGS.map((b) => [b.name, b]));

export function findBuilding(name: string | null): CampusBuilding | undefined {
  return name ? BY_NAME.get(name) : undefined;
}

export const CATEGORY_LABELS: Record<string, string> = {
  wifi: "WiFi & Network",
  electrical: "Electrical",
  sanitation: "Sanitation",
  infrastructure: "Infrastructure",
  academics: "Academics",
  other: "Other",
};

export function categoryLabel(slug: string | null): string {
  if (!slug) return "Uncategorized";
  return CATEGORY_LABELS[slug] ?? slug;
}

export const CATEGORY_SLUGS = Object.keys(CATEGORY_LABELS);
