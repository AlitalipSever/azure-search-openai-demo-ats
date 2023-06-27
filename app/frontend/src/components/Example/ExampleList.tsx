import { Example } from "./Example";

import styles from "./Example.module.css";

export type ExampleModel = {
    text: string;
    value: string;
};

const EXAMPLES: ExampleModel[] = [
    {
        text: "Can you share any success stories of your digital transformation solutions in action?",
        value: "Can you share any success stories or case studies of your digital transformation solutions in action? How did your company help a client achieve their goals through innovative technological advancements?"
    },
    { text: "Do you have any references from previous clients who have undergone digital transformation with your company?",
    value: "Do you have any references or testimonials from previous clients who have undergone digital transformation with your company?" },
    { text: "How your digital transformation services have made a significant impact on businesses.", value: "I'm interested in learning about real-world examples of how your digital transformation services have made a significant impact on businesses. Could you provide a specific case study where your company's expertise revolutionized a client's operations, leading to increased efficiency, cost savings, or improved customer experience?" }
];

interface Props {
    onExampleClicked: (value: string) => void;
}

export const ExampleList = ({ onExampleClicked }: Props) => {
    return (
        <ul className={styles.examplesNavList}>
            {EXAMPLES.map((x, i) => (
                <li key={i}>
                    <Example text={x.text} value={x.value} onClick={onExampleClicked} />
                </li>
            ))}
        </ul>
    );
};
