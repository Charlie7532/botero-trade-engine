import MediaBlock from '@/components/TestComponents/MediaBlock';
import HeroBlock from '@/components/TestComponents/HeroBlock';

interface CalculadoraProps {
    x: number;
    y: number;
}

const Calculadora = ({ x, y }: CalculadoraProps) => {
    const z: number = x + y;
    return (
        <div>el valor calculado es: {z}</div>
    )
}

const HeroInvestors = () => {
    const y: string = new Date().toLocaleDateString('en-US', {
        // year: 'numeric',
        month: 'short',
        day: 'numeric'
    });

    return (
        <section id="HeroInvestors" className="flex flex-col items-start justify-center gap-4 py-8 md:pt-20 px-12">
            <div className="container mx-auto flex flex-col items-start max-w-5xl">
                <HeroBlock
                    title="Main Title"
                    highlightedText="Highlighted Text"
                    secondaryTitle="Secondary Title"
                    description="This is a test description for Andres's training component."
                    href="https://app.nubi.com.co/simulate/investment"
                    ButtonText="Buy Now"
                />


                <MediaBlock
                    alt="test app preview"
                    imagen="/assets/images/colibri.jpeg"
                />


                <HeroBlock
                    title="Main Title"
                    highlightedText="Highlighted Text"
                    secondaryTitle="Secondary Title"
                    description="This is a test description for Andres's training component."
                    href="https://app.nubi.com.co/simulate/investment"
                    ButtonText={`Hoy es: ${y}`}
                    className="mt-20"
                />

                <Calculadora x={10} y={200} />
            </div>
        </section>
    )
}

export default HeroInvestors;