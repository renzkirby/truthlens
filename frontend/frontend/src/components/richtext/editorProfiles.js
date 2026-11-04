export const RICH_TEXT_PROFILES = Object.freeze({
   discussion: Object.freeze({
      headings: [],
      orderedList: true,
      underline: false,
      undoRedo: false,
      compact: false,
   }),
   evidence: Object.freeze({
      headings: [],
      orderedList: true,
      underline: false,
      undoRedo: false,
      compact: false,
   }),
   comment: Object.freeze({
      headings: [],
      orderedList: false,
      underline: false,
      undoRedo: false,
      compact: true,
   }),
   publication: Object.freeze({
      headings: [2, 3],
      orderedList: true,
      underline: true,
      undoRedo: true,
      compact: false,
   }),
});

export function getRichTextProfile(profile) {
   return RICH_TEXT_PROFILES[profile] || RICH_TEXT_PROFILES.discussion;
}
