export const COMMUNITY_REPORT_REASONS = [
   {
      value: "SPAM",
      label: "Spam or unwanted promotion",
      description: "Repetitive messages, irrelevant advertising, mass promotion, or disruptive posting.",
   },
   {
      value: "HARASSMENT",
      label: "Harassment or bullying",
      description: "Targeted abuse, intimidation, repeated personal attacks, or coordinated harassment.",
   },
   {
      value: "HATE",
      label: "Hate or discrimination",
      description: "Degrading or abusive content targeting protected or intrinsic characteristics.",
   },
   {
      value: "VIOLENCE_DANGEROUS",
      label: "Violence, threats, or dangerous content",
      description: "Threats, incitement, or encouragement of serious physical harm or dangerous behavior.",
      sensitive: true,
   },
   {
      value: "PRIVACY",
      label: "Sharing private information",
      description: "Non-public addresses, contact details, credentials, personal records, or other sensitive information.",
   },
   {
      value: "SEXUAL_EXPLOITATIVE",
      label: "Sexual or exploitative content",
      description: "Non-consensual intimate material, sexual exploitation, or seriously abusive sexual content.",
      sensitive: true,
   },
   {
      value: "IMPERSONATION_FRAUD",
      label: "Impersonation, scam, or fraud",
      description: "Fake identity or representation, phishing, fraudulent offers, deceptive links, or attempts to obtain money, credentials, or personal information.",
   },
   {
      value: "OTHER",
      label: "Others",
      description: "Something concerning that does not clearly fit the options above.",
   },
];
