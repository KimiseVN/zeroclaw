import Header       from "@/components/Header";
import Hero         from "@/components/sections/Hero";
import HomeSections from "@/components/sections/HomeSections";
import Footer       from "@/components/sections/Footer";

export default function HomePage() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        <HomeSections />
      </main>
      <Footer />
    </>
  );
}
