"use client";
import { Fragment, type ReactElement } from "react";
import { useSectionOrder, type SectionId } from "@/lib/use-site-settings";
import Features       from "./Features";
import Demo           from "./Demo";
import Pricing        from "./Pricing";
import Download       from "./Download";
import ReferralBanner from "./ReferralBanner";
import VisitorStats   from "./VisitorStats";
import Faq            from "./Faq";
import SupportHours   from "./SupportHours";

const SECTIONS: Record<SectionId, ReactElement> = {
  features:        <Features />,
  demo:            <Demo />,
  pricing:         <Pricing />,
  download:        <Download />,
  referral_banner: <ReferralBanner />,
  visitor_stats:   <VisitorStats />,
  faq:             <Faq />,
  support_hours:   <SupportHours />,
};

export default function HomeSections() {
  const { order, hidden } = useSectionOrder();

  return (
    <>
      {order
        .filter(id => !hidden.includes(id))
        .map(id => (
          <Fragment key={id}>{SECTIONS[id] ?? null}</Fragment>
        ))}
    </>
  );
}
