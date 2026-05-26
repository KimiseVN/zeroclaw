export type Lang = "en" | "vi";

export const T = {
  nav: {
    features: { en: "Features",  vi: "Tính năng" },
    demo:     { en: "Demo",      vi: "Demo"       },
    pricing:  { en: "Pricing",   vi: "Bảng giá"   },
    download: { en: "Download",  vi: "Tải xuống"  },
    faq:      { en: "FAQ",       vi: "FAQ"         },
    hours:    { en: "Hours",     vi: "Giờ hỗ trợ" },
    buyNow:   { en: "Buy Now",   vi: "Mua ngay"   },
  },

  hero: {
    eyebrow: {
      en: "Overlay companion for Where Winds Meet",
      vi: "Overlay đồng hành cho Where Winds Meet",
    },
    h1: {
      en: "Ping. FPS. Events.\nAll in one.",
      vi: "Ping. FPS. Sự kiện.\nTất cả trong một.",
    },
    lead: {
      en: "WWM Overlay displays network stats, performance metrics, Guild event schedule and Quest Helper right while playing — no game injection, no anti-cheat interference.",
      vi: "WWM Overlay hiển thị thông số mạng, hiệu suất, lịch sự kiện Guild và Quest Helper ngay khi chơi game — không can thiệp game, không ảnh hưởng anti-cheat.",
    },
    trust: {
      antiCheat: { title: { en: "Anti-cheat safe", vi: "An toàn anti-cheat" }, sub: { en: "No DLL injection", vi: "Không inject DLL" } },
      autoUpdate: { title: { en: "Auto update", vi: "Tự động cập nhật" }, sub: { en: "Auto updates on startup", vi: "Cập nhật khi khởi động" } },
      lang:       { title: { en: "EN / VI", vi: "EN / VI" }, sub: { en: "Supports 2 languages", vi: "Hỗ trợ 2 ngôn ngữ" } },
    },
  },

  features: {
    eyebrow: { en: "Features",   vi: "Tính năng" },
    heading: {
      en: "Everything you need,\nright on screen.",
      vi: "Mọi thứ bạn cần,\nngay trên màn hình.",
    },
    lead: {
      en: "Designed to use minimal resources, not obstruct gameplay, easily toggled with hotkeys.",
      vi: "Thiết kế nhẹ, không cản gameplay, dễ bật/tắt bằng phím tắt.",
    },
    cards: [
      {
        title: { en: "Network Monitor",    vi: "Giám sát mạng"     },
        desc:  { en: "Real-time ping per game process, packet loss, jitter, min/max — updated every second.", vi: "Ping theo tiến trình game, packet loss, jitter, min/max — cập nhật mỗi giây." },
        tags: ["Ping","Loss","Jitter","Server IP"],
      },
      {
        title: { en: "Performance",        vi: "Hiệu suất"         },
        desc:  { en: "FPS, frame time, 1% Low. CPU/GPU temp, RAM, VRAM — pinned to the GPU rendering your game.", vi: "FPS, thời gian khung, 1% Low. Nhiệt độ CPU/GPU, RAM, VRAM — gắn với GPU render game." },
        tags: ["FPS","CPU Temp","GPU Temp","VRAM"],
      },
      {
        title: { en: "Guild Events",       vi: "Sự kiện Guild"     },
        desc:  { en: "Load event schedule by Guild ID, show countdown to the next event directly on the overlay.", vi: "Tải lịch sự kiện theo Guild ID, hiện đếm ngược sự kiện tiếp theo trực tiếp trên overlay." },
        tags: ["Guild ID","Countdown","Auto refresh"],
      },
      {
        title: { en: "Quest Helper",       vi: "Quest Helper"      },
        desc:  { en: "Press hotkey → screen scan → OCR quest name → show EN/VI walkthrough on the overlay. Never leave the game.", vi: "Nhấn phím tắt → quét màn hình → OCR tên quest → hiển thị hướng dẫn EN/VI. Không cần rời game." },
        tags: ["OCR","Wandering Tales","EN/VI"],
      },
      {
        title: { en: "Encounter Tracker",  vi: "Encounter Tracker" },
        desc:  { en: "WWM encounter database with detailed info. Look up boss and enemy data without leaving the game.", vi: "Cơ sở dữ liệu encounter WWM với thông tin chi tiết. Tra cứu boss và kẻ thù mà không cần rời game." },
        tags: ["Encounter DB","Auto cache"],
      },
      {
        title: { en: "Game Tweaks",        vi: "Tối ưu Game"       },
        desc:  { en: "Optimize Windows registry for gaming: reduce input lag, disable Superfetch, ultimate performance mode.", vi: "Tối ưu registry Windows cho gaming: giảm input lag, tắt Superfetch, chế độ hiệu suất tối đa." },
        tags: ["Input lag","Performance","Registry"],
      },
    ],
  },

  pricing: {
    eyebrow: { en: "Pricing",             vi: "Bảng giá"           },
    heading: { en: "Choose your plan.",   vi: "Chọn gói phù hợp."  },
    lead:    {
      en: "Free {trial} trial on first launch. After trial, choose a plan to unlock all features.",
      vi: "Dùng thử {trial} miễn phí khi chạy lần đầu. Sau thử nghiệm, chọn gói để mở khóa toàn bộ tính năng.",
    },
    addToCart: { en: "Add to Cart",       vi: "Thêm vào giỏ"       },
    note:      {
      en: "Prices in USD · PayPal, Stripe, Crypto, Bank transfer accepted · License tied to device HWID ·",
      vi: "Giá tính bằng USD · Chấp nhận PayPal, Stripe, Crypto, chuyển khoản · License gắn với HWID thiết bị ·",
    },
    modal: {
      title:     { en: "Before you buy",         vi: "Trước khi mua"         },
      steps: [
        { label: { en: "Sign in & checkout",     vi: "Đăng nhập & thanh toán"  },
          hint:  { en: "Login with Google, select a payment method on the checkout page.", vi: "Đăng nhập Google, chọn phương thức thanh toán trên trang checkout." } },
        { label: { en: "Complete your payment",  vi: "Hoàn tất thanh toán"     },
          hint:  { en: "PayPal, Stripe, crypto, or Vietnamese bank transfer — your choice.", vi: "PayPal, Stripe, crypto, hoặc chuyển khoản ngân hàng Việt Nam — tùy bạn." } },
        { label: { en: "Receive key within 1 h", vi: "Nhận key trong vòng 1 giờ" },
          hint:  { en: "Admin verifies and sends the key to your dashboard automatically.", vi: "Admin xác minh và gửi key vào dashboard của bạn tự động." } },
      ],
      verify:    { en: "License keys are issued by admin after payment verification.", vi: "License key được admin phát hành sau khi xác minh thanh toán." },
      confirm:   { en: "Add to Cart →",          vi: "Thêm vào giỏ →"         },
      cancel:    { en: "Cancel",                 vi: "Hủy"                    },
    },
  },

  download: {
    eyebrow:   { en: "Download",                   vi: "Tải xuống"              },
    heading:   { en: "Get started now.",            vi: "Bắt đầu ngay."          },
    lead:      { en: "Single exe, no installation needed. Run as Administrator to read PresentMon metrics.", vi: "File exe đơn, không cần cài đặt. Chạy với quyền Administrator để đọc chỉ số PresentMon." },
    reqs: [
      { en: "Windows 10/11 (64-bit)",             vi: "Windows 10/11 (64-bit)"  },
      { en: "First run requires Admin privileges", vi: "Lần đầu cần quyền Admin" },
      { en: "No .NET or runtime required",        vi: "Không cần .NET hay runtime" },
    ],
    discord:     { en: "Discord",                  vi: "Discord"                },
    latest:      { en: "Latest release",           vi: "Phiên bản mới nhất"     },
    stable:      { en: "Stable",                   vi: "Ổn định"                },
    refPlaceholder: { en: "Referral code (optional)", vi: "Mã giới thiệu (tùy chọn)" },
    refApplied:  { en: "Applied",                  vi: "Đã áp dụng"             },
    dlBtn:       { en: "Download PingOverlay.exe", vi: "Tải PingOverlay.exe"    },
    help:        { en: "Need help? Contact us on Discord →", vi: "Cần hỗ trợ? Liên hệ Discord →" },
    smartscreen: {
      en: `Windows SmartScreen may warn — click "More info → Run anyway" to continue.`,
      vi: `Windows SmartScreen có thể cảnh báo — nhấn "More info → Run anyway" để tiếp tục.`,
    },
  },

  supportHours: {
    eyebrow: { en: "Support Hours",    vi: "Giờ hỗ trợ"               },
    heading: { en: "When we're online.", vi: "Khi nào chúng tôi trực." },
    lead:    {
      en: "Available every day. Leave a message anytime — we reply within working hours.",
      vi: "Hoạt động mỗi ngày. Nhắn tin bất cứ lúc nào — chúng tôi trả lời trong giờ làm việc.",
    },
    online:        { en: "Currently online",       vi: "Đang trực tuyến"          },
    offline:       { en: "Outside working hours",  vi: "Ngoài giờ làm việc"       },
    every:         { en: "Every day",              vi: "Mỗi ngày"                 },
    now:           { en: "Now:",                   vi: "Hiện tại:"                },
    alwaysOnline:  { en: "Always online · 24/7",   vi: "Luôn trực tuyến · 24/7"   },
    window247:     { en: "00:00 – 24:00",          vi: "00:00 – 24:00"            },
    daily247:      { en: "Every day, all day",     vi: "Mỗi ngày, cả ngày"        },
    lead247: {
      en: "Available 24 hours a day, 7 days a week — we're always here when you need us.",
      vi: "Hoạt động 24 giờ mỗi ngày, 7 ngày mỗi tuần — chúng tôi luôn sẵn sàng hỗ trợ bạn.",
    },
  },

  footer: {
    tagline: {
      en: "The ultimate performance overlay for Where Winds Meet.",
      vi: "Overlay hiệu suất tốt nhất cho Where Winds Meet.",
    },
    product:  { en: "Product",  vi: "Sản phẩm"    },
    support:  { en: "Support",  vi: "Hỗ trợ"      },
    account:  { en: "Account",  vi: "Tài khoản"   },
    legal:    { en: "Legal",    vi: "Pháp lý"      },
    features: { en: "Features", vi: "Tính năng"   },
    demo:     { en: "Demo",     vi: "Demo"         },
    pricing:  { en: "Pricing",  vi: "Bảng giá"    },
    download: { en: "Download", vi: "Tải xuống"   },
    faq:          { en: "FAQ",              vi: "FAQ"              },
    hours:        { en: "Support Hours",    vi: "Giờ hỗ trợ"      },
    discordServer:{ en: "Discord Server",   vi: "Discord Server"   },
    myLicenses:   { en: "My Licenses",      vi: "License của tôi"  },
    orderHistory: { en: "Order History",    vi: "Lịch sử đơn hàng" },
    terms:        { en: "Terms of Service", vi: "Điều khoản dịch vụ" },
    privacy:      { en: "Privacy Policy",   vi: "Chính sách bảo mật" },
    cookieSettings: { en: "Cookie Settings", vi: "Cài đặt Cookie"  },
    termsShort:   { en: "Terms",    vi: "Điều khoản" },
    privacyShort: { en: "Privacy",  vi: "Bảo mật"    },
  },

  ref: {
    inviteBadge: { en: "🎁 You've been invited!", vi: "🎁 Bạn được mời tham gia!" },
    heroAccent:  { en: "Best overlay", vi: "Overlay tốt nhất" },
    heroSuffix:  { en: "for Where Winds Meet", vi: "cho Where Winds Meet" },
    heroSub:     {
      en: "Real-time ping, quest tracker & event monitor. {trial} free trial — no installation.",
      vi: "Ping, quest tracker & event monitor real-time. Dùng thử {trial} miễn phí — không cài đặt.",
    },
    codeLabel:  { en: "Referral code",      vi: "Mã giới thiệu"    },
    copyCode:   { en: "Copy code",          vi: "Sao chép mã"      },
    copied:     { en: "✓ Copied",           vi: "✓ Đã sao chép"    },
    dlBtn:      { en: "Download Free — PingOverlay.exe", vi: "Tải miễn phí — PingOverlay.exe" },
    smartscreen:{
      en: `Windows SmartScreen may warn — click "More info → Run anyway"`,
      vi: `Windows SmartScreen có thể cảnh báo — nhấn "More info → Run anyway"`,
    },
    features: [
      {
        icon: "📡",
        title: { en: "Real-time Ping",   vi: "Ping Thời Gian Thực"    },
        desc:  { en: "Monitor your ping with millisecond precision directly in-game.", vi: "Theo dõi ping với độ chính xác mili giây ngay trong game." },
      },
      {
        icon: "🗺️",
        title: { en: "Quest Tracker",    vi: "Theo Dõi Quest"          },
        desc:  { en: "Auto-detect and highlight active quests so you never miss objectives.", vi: "Tự động phát hiện và làm nổi bật quest đang hoạt động — không bỏ lỡ mục tiêu." },
      },
      {
        icon: "⚡",
        title: { en: "Event Monitor",    vi: "Theo Dõi Sự Kiện"        },
        desc:  { en: "Get notified of world events the moment they start — never miss rare drops.", vi: "Nhận thông báo sự kiện thế giới ngay khi bắt đầu — không bỏ lỡ vật phẩm hiếm." },
      },
      {
        icon: "🪟",
        title: { en: "Overlay Window",   vi: "Cửa Sổ Overlay"          },
        desc:  { en: "Always-on-top transparent overlay — zero impact on game performance.", vi: "Overlay trong suốt luôn hiển thị — không ảnh hưởng hiệu suất game." },
      },
    ],
    howTitle: { en: "How the referral works", vi: "Chương trình giới thiệu hoạt động như thế nào" },
    step1:    { en: "You download & try WWM Overlay using this referral code.", vi: "Bạn tải và dùng thử WWM Overlay bằng mã giới thiệu này." },
    step2:    { en: "Your friend earns +{n} point for the download.", vi: "Người giới thiệu nhận +{n} điểm cho mỗi lượt tải." },
    step3:    { en: "Buy a license with their code → both earn +{n} points.", vi: "Mua license bằng mã → cả hai cùng nhận +{n} điểm." },
    step4:    { en: "Reach {pts} points → free {days}-day license for your friend!", vi: "Đạt {pts} điểm → người giới thiệu nhận license {days} ngày miễn phí!" },
    ctaTitle: { en: "Ready to play smarter?",                          vi: "Sẵn sàng chơi thông minh hơn?"               },
    ctaSub:   { en: "Download now, enjoy {trial} free. No payment needed to try.", vi: "Tải ngay, dùng thử {trial} miễn phí. Không cần thanh toán." },
    ctaBtn:   { en: "Download PingOverlay.exe",                        vi: "Tải PingOverlay.exe"                          },

    /* ReferralBanner (shown on landing page for logged-in users) */
    bannerEyebrow: { en: "Referral Program",                vi: "Chương Trình Giới Thiệu"                  },
    bannerTitle:   { en: "Invite friends — earn a ",        vi: "Giới thiệu bạn bè — nhận "                },
    bannerAccent:  { en: "free license",                    vi: "license miễn phí"                         },
    bannerSub:     {
      en: "Share your link. Earn {dl} pt per download, {pur} pts per purchase. Reach {pts} pts → free {days}-day license.",
      vi: "Chia sẻ link của bạn. Nhận {dl} điểm/lượt tải, {pur} điểm/lượt mua. Đạt {pts} điểm → license {days} ngày miễn phí.",
    },
    cardCodeLabel: { en: "Your referral code",              vi: "Mã giới thiệu của bạn"                    },
    cardLinkLabel: { en: "Referral link",                   vi: "Link giới thiệu"                          },
  },

  dashboard: {
    title:      { en: "My Dashboard",  vi: "Trang cá nhân" },
    buyLicense: { en: "Buy License",   vi: "Mua License"   },
    stats: {
      activeLicenses: { en: "Active Licenses",  vi: "License đang dùng" },
      totalLicenses:  { en: "Total Licenses",   vi: "Tổng license"       },
      referralPoints: { en: "Referral Points",  vi: "Điểm giới thiệu"   },
      totalOrders:    { en: "Total Orders",     vi: "Tổng đơn hàng"     },
    },
    tabs: {
      licenses: { en: "Licenses",   vi: "License"     },
      orders:   { en: "Orders",     vi: "Đơn hàng"    },
      inbox:    { en: "Inbox",      vi: "Hộp thư"     },
      referral: { en: "Referral",   vi: "Giới thiệu"  },
      account:  { en: "My Account", vi: "Tài khoản"   },
    },
    licenses: {
      empty:    { en: "No licenses yet.",  vi: "Chưa có license nào."  },
      get:      { en: "Get a License",     vi: "Mua License"            },
      issued:   { en: "Issued:",           vi: "Ngày cấp:"              },
      lifetime: { en: "Lifetime",          vi: "Vĩnh viễn"              },
      expired:  { en: "Expired",           vi: "Hết hạn"                },
      daysLeft: { en: "d left",            vi: "ngày còn lại"           },
      statusActive:  { en: "Active",   vi: "Đang dùng"   },
      statusExpired: { en: "Expired",  vi: "Hết hạn"     },
      statusRevoked: { en: "Revoked",  vi: "Đã thu hồi"  },
    },
    orders: {
      empty: { en: "No orders yet.", vi: "Chưa có đơn hàng nào." },
      date:   { en: "Date",   vi: "Ngày"         },
      plan:   { en: "Plan",   vi: "Gói"          },
      amount: { en: "Amount", vi: "Số tiền"      },
      method: { en: "Method", vi: "Thanh toán"   },
      ref:    { en: "Ref",    vi: "Mã giao dịch" },
      status: { en: "Status", vi: "Trạng thái"   },
    },
    inbox: {
      notification:  { en: "notification",  vi: "thông báo" },
      notifications: { en: "notifications", vi: "thông báo" },
      unread:        { en: "unread",        vi: "chưa đọc"  },
      markAllRead:   { en: "Mark all read", vi: "Đánh dấu đã đọc" },
      empty:         { en: "No notifications yet.", vi: "Chưa có thông báo nào." },
    },
    referral: {
      codeTitle:    { en: "Referral Code",   vi: "Mã giới thiệu"      },
      codeSub:      { en: "Share your referral link. Earn points when friends download or buy a license. Accumulate enough points to earn a free 30-day license!", vi: "Chia sẻ link giới thiệu của bạn. Kiếm điểm khi bạn bè tải về hoặc mua license. Tích đủ điểm để nhận license 30 ngày miễn phí!" },
      copyCode:     { en: "Copy code",       vi: "Sao chép mã"        },
      copied:       { en: "✓ Copied",        vi: "✓ Đã sao chép"      },
      linkLabel:    { en: "Your referral link", vi: "Link giới thiệu của bạn" },
      copyLink:     { en: "Copy link",       vi: "Sao chép link"      },
      copiedLink:   { en: "✓ Copied!",       vi: "✓ Đã sao chép!"     },
      msgLabel:     { en: "Share message",   vi: "Tin nhắn chia sẻ"   },
      copyMsg:      { en: "📋 Copy message", vi: "📋 Sao chép tin nhắn" },
      copiedMsg:    { en: "✓ Message copied!", vi: "✓ Đã sao chép tin nhắn!" },
      generating:   { en: "Referral code is being generated. Refresh the page in a moment.", vi: "Mã giới thiệu đang được tạo. Hãy tải lại trang sau giây lát." },
      pointsTitle:  { en: "Referral Points", vi: "Điểm giới thiệu"    },
      totalPoints:  { en: "Total Points",    vi: "Tổng điểm"          },
      downloads:    { en: "Downloads",       vi: "Lượt tải"           },
      purchases:    { en: "Purchases",       vi: "Lượt mua"           },
      progressLabel:{ en: "pts → free",    vi: "điểm → license"   },
      progressDay:  { en: "-day license", vi: " ngày miễn phí"   },
      recentActivity:{ en: "Recent activity", vi: "Hoạt động gần đây" },
      purchaseRef:  { en: "Purchase referral", vi: "Giới thiệu mua hàng" },
      downloadRef:  { en: "Download referral", vi: "Giới thiệu tải về"   },
      pts:          { en: "pts",             vi: "điểm"               },
    },
    account: {
      profileTitle:       { en: "Profile",          vi: "Hồ sơ"                    },
      memberSince:        { en: "Member since",     vi: "Thành viên từ"             },
      fullName:           { en: "Full Name",         vi: "Họ và tên"                },
      namePlaceholder:    { en: "Your name",         vi: "Tên của bạn"              },
      emailLabel:         { en: "Email address",     vi: "Địa chỉ email"            },
      emailHint:          { en: "Email cannot be changed here. Contact support if needed.", vi: "Email không thể thay đổi tại đây. Liên hệ hỗ trợ nếu cần." },
      saving:             { en: "Saving…",           vi: "Đang lưu…"               },
      saveChanges:        { en: "Save Changes",      vi: "Lưu thay đổi"            },
      saved:              { en: "Saved!",             vi: "Đã lưu!"                 },
      passwordTitle:      { en: "Change Password",   vi: "Đổi mật khẩu"            },
      passwordSub:        { en: "Leave blank to keep your current password.", vi: "Để trống để giữ nguyên mật khẩu hiện tại." },
      newPassword:        { en: "New Password",      vi: "Mật khẩu mới"            },
      passPlaceholder:    { en: "Min. 8 characters", vi: "Tối thiểu 8 ký tự"       },
      confirmPassword:    { en: "Confirm New Password", vi: "Xác nhận mật khẩu mới" },
      confirmPlaceholder: { en: "Repeat password",   vi: "Nhập lại mật khẩu"       },
      updating:           { en: "Updating…",         vi: "Đang cập nhật…"          },
      updatePassword:     { en: "Update Password",   vi: "Cập nhật mật khẩu"       },
      passUpdated:        { en: "Password updated!", vi: "Đã cập nhật mật khẩu!"   },
      errEmpty:           { en: "Enter a new password.", vi: "Vui lòng nhập mật khẩu mới." },
      errShort:           { en: "Password must be at least 8 characters.", vi: "Mật khẩu phải có ít nhất 8 ký tự." },
      errMatch:           { en: "Passwords do not match.", vi: "Mật khẩu không khớp." },
    },
    timeAgo: {
      justNow: { en: "just now",   vi: "vừa xong"    },
      mAgo:    { en: "m ago",      vi: "phút trước"  },
      hAgo:    { en: "h ago",      vi: "giờ trước"   },
      dAgo:    { en: "d ago",      vi: "ngày trước"  },
    },
  },
} as const;

export function t<K extends keyof typeof T>(
  section: K,
  path: string[],
  lang: Lang,
): string {
  let node: any = T[section];
  for (const key of path) node = node?.[key];
  return (node as any)?.[lang] ?? (node as any)?.en ?? "";
}
