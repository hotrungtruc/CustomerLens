/**
 * CustomerLens 2-Letter Customer Segmentation & ID Display System
 *
 * System Rules:
 * • 1st Letter — Income & Spending Power:
 *     • H (High): Thu nhập cao, chi tiêu mạnh tay (VIP/Premium)
 *     • M (Medium): Thu nhập trung bình, chi tiêu hợp lý (Mass/Middle)
 *     • L (Low): Thu nhập thấp, nhạy cảm về giá (Budget)
 * • 2nd Letter — Behavior & Loyalty:
 *     • L (Loyal): Khách quen, quay lại nhiều lần, gắn bó lâu dài
 *     • C (Casual): Khách vãng lai, thỉnh thoảng mới ghé
 *     • N (New): Khách hàng mới tinh, lần đầu trải nghiệm (Mặc định)
 *
 * Default input for newly detected guests: "LN" (e.g. LN1, LN2...)
 */

export const SEGMENT_DEFINITIONS = {
  HL: {
    code: "HL",
    title: "VIP • Loyal Member",
    incomeTier: "H (High Income / VIP)",
    loyaltyTier: "L (Loyal / Khách quen)",
    badgeColor: "border-amber-400 text-amber-300 bg-amber-950/40",
  },
  HC: {
    code: "HC",
    title: "VIP • Casual Visitor",
    incomeTier: "H (High Income / VIP)",
    loyaltyTier: "C (Casual / Vãng lai)",
    badgeColor: "border-purple-400 text-purple-300 bg-purple-950/40",
  },
  HN: {
    code: "HN",
    title: "VIP • New Customer",
    incomeTier: "H (High Income / VIP)",
    loyaltyTier: "N (New / Khách mới)",
    badgeColor: "border-rose-400 text-rose-300 bg-rose-950/40",
  },
  ML: {
    code: "ML",
    title: "Mass • Loyal Member",
    incomeTier: "M (Medium / Tiêu chuẩn)",
    loyaltyTier: "L (Loyal / Khách quen)",
    badgeColor: "border-emerald-400 text-emerald-300 bg-emerald-950/40",
  },
  MC: {
    code: "MC",
    title: "Mass • Casual Visitor",
    incomeTier: "M (Medium / Tiêu chuẩn)",
    loyaltyTier: "C (Casual / Vãng lai)",
    badgeColor: "border-cyan-400 text-cyan-300 bg-cyan-950/40",
  },
  MN: {
    code: "MN",
    title: "Mass • New Customer",
    incomeTier: "M (Medium / Tiêu chuẩn)",
    loyaltyTier: "N (New / Khách mới)",
    badgeColor: "border-sky-400 text-sky-300 bg-sky-950/40",
  },
  LL: {
    code: "LL",
    title: "Budget • Loyal",
    incomeTier: "L (Low / Tiết kiệm)",
    loyaltyTier: "L (Loyal / Khách quen)",
    badgeColor: "border-blue-400 text-blue-300 bg-blue-950/40",
  },
  LC: {
    code: "LC",
    title: "Budget • Casual",
    incomeTier: "L (Low / Tiết kiệm)",
    loyaltyTier: "C (Casual / Vãng lai)",
    badgeColor: "border-slate-400 text-slate-300 bg-slate-900/60",
  },
  LN: {
    code: "LN",
    title: "Budget • New Guest",
    incomeTier: "L (Low / Tiết kiệm)",
    loyaltyTier: "N (New / Khách mới tinh)",
    badgeColor: "border-cyan-400/80 text-cyan-200 bg-cyan-950/40",
  },
};

/**
 * Derives the 2-letter classification code from customer profile.
 * Returns null if the face has not yet been resolved/saved in the database.
 */
export function getCustomerSegment(customer) {
  if (!customer || (!customer.id && !customer.customer_id) || customer.detected === false) {
    return null;
  }

  // If backend already computed segment_code, use it
  if (customer.segment_code && SEGMENT_DEFINITIONS[customer.segment_code]) {
    return SEGMENT_DEFINITIONS[customer.segment_code];
  }

  // First letter: Income Tier
  const tier = String(customer.loyalty_tier || customer.standing || "").toUpperCase();
  const category = String(customer.service_category || customer.major || "").toUpperCase();
  const spending = Number(customer.total_spending || 0);

  let first = "L";
  if (tier.includes("VIP") || tier.includes("DIAMOND") || category.includes("PREMIUM") || spending >= 10000000) {
    first = "H";
  } else if (tier.includes("GOLD") || tier.includes("SILVER") || tier.includes("MASS") || tier.includes("MIDDLE") || spending >= 2000000) {
    first = "M";
  }

  // Second letter: Loyalty & Behavior (visits)
  const visits = Number(customer.total_visits || customer.total_attendance || customer.visit_count || 0);
  const tenure = Number(customer.tenure || customer.customer_tenure_years || 0);

  let second = "N";
  if (visits >= 5 || tenure >= 2) {
    second = "L";
  } else if (visits > 1) {
    second = "C";
  }

  const code = `${first}${second}`;
  return SEGMENT_DEFINITIONS[code] || SEGMENT_DEFINITIONS.LN;
}

/**
 * Extracts number from ID (e.g. 'LN1' -> '1', 'GUEST_0_0002' -> '2', '005' -> '5')
 */
export function extractCustomerNumber(id) {
  if (!id) return null;
  const match = String(id).match(/(\d+)$/);
  return match ? parseInt(match[1], 10) : id;
}

/**
 * Returns a short, clean, non-colliding ID string (e.g. LN1, LC1, LL1, MN1, HL1)
 * Returns null if embedding has not yet been extracted/saved.
 */
export function formatCustomerDisplayId(customer, face) {
  if (!customer || (!customer.id && !customer.customer_id) || customer.detected === false) {
    return null;
  }

  if (customer.display_id) {
    return customer.display_id;
  }

  const rawId = String(customer.customer_id || customer.id || "");
  const num = extractCustomerNumber(rawId);
  const segment = getCustomerSegment(customer) || SEGMENT_DEFINITIONS.LN;

  if (num !== null && num !== undefined) {
    return `${segment.code}${num}`;
  }

  return rawId || null;
}

/**
 * Returns clean customer name for display
 */
export function getCustomerDisplayName(customer, face) {
  if (!customer || (!customer.id && !customer.customer_id) || customer.detected === false) {
    return "Đang nhận diện...";
  }

  const hasRealName =
    customer?.name &&
    customer.name.trim() !== "" &&
    customer.name !== "Guest" &&
    customer.name !== "Khách mới" &&
    !customer.name.startsWith("Khách LN") &&
    !customer.name.startsWith("Khách LC");

  if (hasRealName) {
    return customer.name;
  }

  const shortId = formatCustomerDisplayId(customer, face);
  return shortId ? `Khách ${shortId}` : "Khách mới";
}
