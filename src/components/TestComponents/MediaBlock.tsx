import Image from 'next/image';

interface MediaProps {
    imagen: string;
    alt: string;
}


const MediaBlock = ({ imagen, alt }: MediaProps) => {
    return (
        <Image
            alt={alt}
            className="w-full h-auto rounded shadow-md mt-10"
            src={imagen}
            width={500}
            height={300}
        />
    )
}

export default MediaBlock;